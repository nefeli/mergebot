# modified from https://raw.githubusercontent.com/jacobtomlinson/python-container-action/master/Dockerfile
FROM python:3-slim AS builder
ADD . /app
WORKDIR /app

# We are installing a dependency here directly into our app source dir
RUN pip install --target=/app requests PyGithub

RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

# A distroless container image with Python and some basics like SSL certificates
# https://github.com/GoogleContainerTools/distroless
FROM gcr.io/distroless/python3-debian10
COPY --from=builder /app /app
COPY --from=builder /usr/bin/git /usr/bin/git
WORKDIR /app
ENV PYTHONPATH /app
CMD ["/app/mergebot.py"]
