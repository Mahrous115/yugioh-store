# syntax=docker/dockerfile:1

# Single stage, deliberately. A second stage exists to keep a compiler out of the
# runtime image, and this build never needs one: all 46 pinned packages resolve to
# manylinux cp312 wheels, verified with `pip install --only-binary=:all: --dry-run`
# against this exact base image. psycopg is not here either -- it is a test-only
# dependency in requirements-dev.txt -- so there are no PostgreSQL client
# libraries to carry. Adding a builder stage would add build time and a second
# thing to keep in sync in exchange for nothing.
#
# python:3.12-slim, matching the 3.12 the pins were resolved for. Not alpine:
# musl cannot use the manylinux wheels above, so every C extension --
# cryptography, pydantic-core, uvloop, httptools, watchfiles, yarl -- would
# compile from source, needing a toolchain in the image and turning a seconds-long
# build into a minutes-long one.
#
# The tag floats within 3.12: rebuilding picks up Debian security patches, at the
# cost of not being bit-for-bit reproducible. Pin the digest instead if you ever
# need the stronger guarantee.
FROM python:3.12-slim

# Set before anything else: these never change, so they never invalidate a
# downstream layer.
#
# PYTHONUNBUFFERED  - Python block-buffers stdout when it is not a terminal. In a
#                     container that means logs arrive late and, if the container
#                     is killed, are lost entirely. Container Apps collects
#                     stdout, so this is what makes your logs actually show up.
# PYTHONDONTWRITEBYTECODE
#                   - stops CPython writing __pycache__ next to the source at
#                     import. Keeps the filesystem untouched at runtime, which is
#                     what lets you enable a read-only root filesystem later.
# PIP_NO_CACHE_DIR  - pip's wheel cache is dead weight in a layer; nothing will
#                     ever install again at runtime.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# The unprivileged user, created early because this layer never changes.
# --system      : no password ageing, no login shell expectations
# --no-create-home : the app writes nothing, so it needs no home directory
# A fixed uid makes the identity predictable if you ever mount a volume or set
# an explicit runAsUser in a Kubernetes-style manifest.
RUN useradd --system --no-create-home --uid 10001 appuser

# ── Dependencies before source ───────────────────────────────────────────────
#
# This is the ordering that matters. Requirements change rarely; main.py changes
# constantly. Copying only requirements.txt here means an edit to application
# code invalidates just the COPY below and nothing above it -- pip does not run
# again. Copy the source first instead and every one-line change re-downloads
# and reinstalls all 46 packages.
COPY requirements.txt ./

# --only-binary=:all: is a guard, not an optimisation. It is already true today;
# stating it means that if a future dependency bump introduces a package with no
# wheel, the build fails immediately and says so, rather than silently attempting
# to compile and failing later with an opaque missing-compiler error.
RUN pip install --no-cache-dir --only-binary=:all: -r requirements.txt

# ── Source last ──────────────────────────────────────────────────────────────
#
# Everything .dockerignore does not exclude: main.py, models/, routers/,
# services/. Notably NOT .env, tests/, or .venv.
COPY . .

# Drop privileges for everything from here on. It is the last instruction before
# the command on purpose: pip above needed to write to site-packages, and running
# it as appuser would have failed on permissions.
#
# The copied files are owned by root and readable by all, which is exactly what
# is wanted -- the app only reads them, and cannot modify its own code at runtime.
USER appuser

# Documentation only. It publishes no port and changes no behaviour; Container
# Apps routes to whatever ingress target port you configure. Kept because it
# records the default that main.py falls back to when PORT is unset.
EXPOSE 8000

# Exec form, not shell form. Shell form would run this under `/bin/sh -c`, making
# the shell PID 1; it does not forward SIGTERM, so the platform's stop signal
# would be ignored and every shutdown would end in a SIGKILL after the grace
# period. In exec form python is PID 1 and receives the signal directly, which is
# what makes scaling to zero clean.
#
# main.py reads PORT (default 8000) and binds 0.0.0.0 itself, so no arguments are
# needed here and the port stays configurable on a running revision.
#
# No HEALTHCHECK: Container Apps runs its own probes against /health, configured
# on the platform side. A Docker-level healthcheck would be ignored there and
# would only add a second, divergent definition of healthy.
CMD ["python", "main.py"]
