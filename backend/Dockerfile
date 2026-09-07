FROM python:3.12-slim

# T_TEST.8 — output appears as it happens, not when the process ends.
#
# Python block-buffers stdout whenever it is not a terminal, and every command
# worth watching is run through `docker compose exec -T` or a pipe — so a
# fifteen-minute test suite printed nothing at all until it finished and then
# printed everything at once. That reads as a hang, and the honest response to
# a hang is Ctrl-C, which is how a green run gets thrown away.
#
# Set on the image rather than remembered per command: the rule is "the
# process is always visible", and a rule that depends on somebody typing an
# extra flag is a rule that holds until the first time they do not.
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
