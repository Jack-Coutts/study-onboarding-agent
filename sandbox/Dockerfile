# Sandbox for generated converters and their tests (spec section 11.1).
# Build with `onboard check-sandbox --build`; runs use the resulting image ID.
FROM python:3.12-slim@sha256:dddfd7e07f9d15aeeca61529320492139d21cac7f0070c00609243e51e4e0016

RUN pip install --no-cache-dir \
        numpy==2.2.6 \
        pandas==2.2.3 \
        pytest==8.3.5 \
        pyyaml==6.0.2 \
    && useradd --no-create-home --shell /usr/sbin/nologin runner

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/tmp

WORKDIR /tmp
USER runner
