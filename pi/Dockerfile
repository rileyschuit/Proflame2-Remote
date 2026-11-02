# Built on an arm64 runner by .github/workflows/pi.yml. Holds no remote identity or
# credentials: those come in as environment variables on the Pi.
FROM python:3.13-slim-trixie AS build
RUN apt-get update && apt-get install -y --no-install-recommends gcc libc6-dev linux-libc-dev \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /build/
RUN pip wheel --no-cache-dir -r /build/requirements.txt -w /wheels

FROM python:3.13-slim-trixie
COPY --from=build /wheels /wheels
COPY requirements.txt /wheels/
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r /wheels/requirements.txt \
    && rm -rf /wheels
COPY proflame2d /app/proflame2d
WORKDIR /app
RUN useradd --system --uid 10001 --no-create-home proflame2 && install -d -o 10001 /data /run/proflame2
USER 10001
ENV PYTHONUNBUFFERED=1
VOLUME /data
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s \
    CMD ["python", "-m", "proflame2d.healthcheck"]
CMD ["python", "-m", "proflame2d"]
