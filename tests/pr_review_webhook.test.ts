import { afterEach, test, expect } from 'bun:test'
import { createHmac } from 'node:crypto'
import { mkdtemp, mkdir, writeFile, readdir, readFile, rm, stat } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import plugin, { createHandler } from '../.amp/plugins/pr-review'

const roots: string[] = []
afterEach(async () => {
	await Promise.all(roots.splice(0).map((root) => rm(root, { recursive: true, force: true })))
})

async function tempRoot(prefix: string) {
	const root = await mkdtemp(join(tmpdir(), prefix))
	roots.push(root)
	return root
}

async function setup() {
	const root = await tempRoot('onboarding-webhook-test-')
	await mkdir(join(root, '.agents/skills/reviewing-prs/scripts'), { recursive: true })
	await mkdir(join(root, '.agents/skills/reviewing-pr-simplicity'), { recursive: true })
	await writeFile(join(root, '.agents/skills/reviewing-prs/SKILL.md'), 'Trusted test skill')
	await writeFile(join(root, '.agents/skills/reviewing-pr-simplicity/SKILL.md'), 'Trusted follow-up skill')
	await writeFile(join(root, '.agents/skills/reviewing-prs/scripts/post_review.py'), '# Trusted publisher')
	const config = { secret: 'a'.repeat(64), repositoryId: 123 }
	const s = {
		creates: 0, appends: 0, githubCalls: 0, failAppend: false, failCreate: false,
		abortAfterCreate: null as AbortController | null, messages: [] as any[],
		permission: 'write', state: 'open', draft: false, labels: [{ name: 'ready for review' }],
	}
	const thread = {
		id: 'T-test', messages: async () => s.messages,
		appendUserMessage: async (message: any) => {
			s.appends++
			s.messages.push({ role: 'user', content: [{ type: 'text', text: message.content }] })
			if (s.failAppend) { s.failAppend = false; throw new Error('acknowledgement lost') }
		},
	}
	const amp: any = {
		getBuiltinAgent: (mode: string) => {
			expect(mode).toBe('medium')
			return { createThread: async (options: any) => {
				expect(options.executor).toBe('orb')
				s.creates++
				if (s.failCreate) throw new Error('creation outcome unknown')
				s.abortAfterCreate?.abort()
				return thread
			} }
		}, threads: { get: () => thread },
	}
	const github = async (path: string) => {
		s.githubCalls++
		return path.endsWith('/permission') ? { permission: s.permission, user: { id: 7 } } : {
			number: 5, state: s.state, draft: s.draft, labels: s.labels,
			base: { sha: 'b'.repeat(40), repo: { id: 123 } }, head: { sha: 'c'.repeat(40) },
		}
	}
	const ctx: any = { signal: new AbortController().signal, thread: { id: 'T-owner' }, logger: { log() {} } }
	const payload = { repository: { id: 123, full_name: 'Jack-Coutts/study-onboarding-agent' },
		action: 'labeled', number: 5, label: { name: 'ready for review' }, sender: { id: 7, login: 'maintainer' } }
	// Each labelling has its own updated_at, so distinct names give distinct signed bodies.
	const event = (name: string, overrides = {}, eventType = 'pull_request', delivery = name): any => {
		const body = Buffer.from(JSON.stringify({ ...payload, pull_request: { updated_at: name }, ...overrides }))
		return { id: delivery, body, receivedAt: '2026-10-02T00:00:00Z', headers: {
			'x-github-event': eventType, 'x-github-delivery': delivery,
			'x-hub-signature-256': `sha256=${createHmac('sha256', config.secret).update(body).digest('hex')}`,
		} }
	}
	const handler = () => createHandler(amp, root, config, github)
	return { root, s, ctx, event, handler }
}

test('ignores unauthenticated and unrelated events without calling GitHub', async () => {
	const { root, s, ctx, event, handler } = await setup()
	const handle = handler()
	const invalid = event('invalid'); invalid.headers['x-hub-signature-256'] = 'sha256=' + '0'.repeat(64)
	await handle(invalid, ctx)
	const tampered = event('tampered'); tampered.body = Buffer.from('{}')
	await handle(tampered, ctx)
	await handle(event('wrong-repo', { repository: { id: 321, full_name: 'someone/else' } }), ctx)
	await handle(event('wrong-label', { label: { name: 'run-task' } }), ctx)
	await handle(event('wrong-action', { action: 'synchronize' }), ctx)
	await handle(event('ping', {}, 'ping'), ctx)
	expect(s.githubCalls).toBe(0)
	expect(s.creates).toBe(0)
	expect(JSON.parse(await readFile(join(root, '.amp/pr-review/last-ping.json'), 'utf8')).receivedAt).toBeTruthy()
})

test.each([
	['sender lacks write permission', (s: any) => { s.permission = 'read' }, {}],
	['PR is closed', (s: any) => { s.state = 'closed' }, {}],
	['PR is a draft', (s: any) => { s.draft = true }, {}],
	['label was removed', (s: any) => { s.labels = [] }, {}],
	['sender ID does not match the login', () => {}, { sender: { id: 8, login: 'maintainer' } }],
] as const)('does not dispatch when the %s', async (_, change, overrides) => {
	const { s, ctx, event, handler } = await setup()
	change(s)
	await handler()(event('gated', overrides), ctx)
	expect(s.creates).toBe(0)
})

test('rejects a delivery whose handler was already cancelled', async () => {
	const { s, ctx, event, handler } = await setup()
	const cancelled = new AbortController(); cancelled.abort()
	await expect(handler()(event('cancelled'), { ...ctx, signal: cancelled.signal })).rejects.toThrow()
	expect(s.creates).toBe(0)
})

test('dispatches one pinned review per event across concurrency, retries, and reloads', async () => {
	const { root, s, ctx, event, handler } = await setup()
	const handle = handler()
	await Promise.all([handle(event('first'), ctx), handle(event('first'), ctx)])
	await handle(event('first'), ctx)
	await handler()(event('first'), ctx) // Persistent dedupe after reload.
	expect(s.creates).toBe(1); expect(s.appends).toBe(1)
	expect(await readdir(join(root, '.amp/pr-review/events'))).toHaveLength(1)
	const prompt = s.messages[0].content[0].text
	expect(prompt).toContain('Pinned head: ' + 'c'.repeat(40))
	expect(prompt).toContain('Trusted test skill')
	expect(prompt).toContain('NOT sufficient isolation')
	expect(prompt).toContain('Trusted follow-up skill')
	expect(prompt).toContain('# Trusted publisher')
	expect(prompt).toContain('ONLY AFTER the publisher returns the confirmed scientific comment URL')
	expect(prompt).toContain('--stage scientific')
	expect(prompt).toContain('--stage simplicity')
})

test('a signed body replayed under a new delivery ID does not dispatch again', async () => {
	const { s, ctx, event, handler } = await setup()
	await handler()(event('first', {}, 'pull_request', 'delivery-1'), ctx)
	await handler()(event('first', {}, 'pull_request', 'delivery-2'), ctx)
	expect(s.creates).toBe(1); expect(s.appends).toBe(1)
	await handler()(event('relabelled'), ctx)
	expect(s.creates).toBe(2)
})

test('recovers a lost append acknowledgement without a second thread', async () => {
	const { s, ctx, event, handler } = await setup()
	s.failAppend = true
	await expect(handler()(event('lost-ack'), ctx)).rejects.toThrow('acknowledgement lost')
	await handler()(event('lost-ack'), ctx)
	expect(s.creates).toBe(1); expect(s.appends).toBe(1)
})

test('leaves an unknown thread-creation outcome for manual recovery', async () => {
	const { s, ctx, event, handler } = await setup()
	s.failCreate = true
	await expect(handler()(event('unknown-create'), ctx)).rejects.toThrow('creation outcome unknown')
	await handler()(event('unknown-create'), ctx)
	expect(s.creates).toBe(1); expect(s.appends).toBe(0)
})

test('appends after a cancellation that followed thread creation', async () => {
	const { s, ctx, event, handler } = await setup()
	s.abortAfterCreate = new AbortController()
	await expect(handler()(event('cancelled'), { ...ctx, signal: s.abortAfterCreate.signal })).rejects.toThrow()
	s.abortAfterCreate = null
	await handler()(event('cancelled'), ctx)
	expect(s.creates).toBe(1); expect(s.appends).toBe(1)
})

test('rechecks live PR state before recovering an append', async () => {
	const { s, ctx, event, handler } = await setup()
	s.abortAfterCreate = new AbortController()
	await expect(handler()(event('recheck'), { ...ctx, signal: s.abortAfterCreate.signal })).rejects.toThrow()
	s.abortAfterCreate = null
	s.labels = []
	await handler()(event('recheck'), ctx)
	expect(s.appends).toBe(0)
	s.labels = [{ name: 'ready for review' }]
	await handler()(event('recheck'), ctx)
	expect(s.creates).toBe(1); expect(s.appends).toBe(1)
})

test('plugin registers only with local config and persists endpoint privately', async () => {
	const root = await tempRoot('onboarding-webhook-registration-')
	let registrations = 0
	const amp: any = {
		system: { executor: { kind: 'remote' }, workspaceRoot: 'file:///test' },
		helpers: { filePathFromURI: () => root },
		createWebhook: async (options: any) => {
			registrations++
			expect(options.key).toBe('ready-for-review')
			expect(options.headers).toEqual(['x-hub-signature-256', 'x-github-event', 'x-github-delivery'])
			expect(typeof options.handler).toBe('function')
			return { url: 'https://example.invalid/test-only' }
		},
	}
	await plugin(amp)
	expect(registrations).toBe(0)
	await mkdir(join(root, '.amp/pr-review'), { recursive: true })
	await writeFile(join(root, '.amp/pr-review/config.json'), JSON.stringify({ secret: 'a'.repeat(64), repositoryId: 123 }))
	await plugin(amp)
	expect(registrations).toBe(1)
	const path = join(root, '.amp/pr-review/endpoint.json')
	expect(JSON.parse(await readFile(path, 'utf8')).url).toBe('https://example.invalid/test-only')
	expect((await stat(path)).mode & 0o777).toBe(0o600)
})
