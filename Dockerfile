FROM python:3-slim AS builder
WORKDIR /mergebot

RUN pip install --target=/mergebot requests PyGithub jira
RUN apt-get update && apt-get install -y --no-install-recommends git && apt-get purge -y --auto-remove && rm -rf /var/lib/apt/lists/*

ADD mergebot.py /mergebot
RUN chmod +x /mergebot/mergebot.py
CMD ["/mergebot/mergebot.py"]
