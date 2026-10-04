FROM python:3.12-slim AS builder

# WITH_STEP=1 adds the optional 'step' extra (build123d and the OpenCascade
# kernel, 100+ MB) for HexmoHexagon/HexmoRectangle --format step.
ARG WITH_STEP=0

WORKDIR /app

RUN python3 -m venv env
RUN /app/env/bin/pip install gunicorn

# Copy the local fork's source so the venv is built from its requirements,
# not from upstream (which may be missing dependencies added to this fork).
COPY . /app
RUN /app/env/bin/pip install .
RUN if [ "$WITH_STEP" = "1" ]; then /app/env/bin/pip install ".[step]"; fi
RUN mv scripts/boxesserver scripts/boxesserver.py

# ---

FROM python:3.12-slim

ARG WITH_STEP=0

# The OpenCascade kernel needs the OpenGL libraries the slim image lacks.
RUN apt update && \
  apt install -y pstoedit --no-install-recommends && \
  if [ "$WITH_STEP" = "1" ]; then \
    apt install -y libgl1 libglu1-mesa libxrender1 libxext6 --no-install-recommends; \
  fi && \
  apt clean

WORKDIR /app
COPY --from=builder /app /app

CMD ["/app/env/bin/gunicorn",  "-b",  "[::]:8000", "-w", "4", "scripts.boxesserver"]
