#!/bin/bash

docker build -t ghcr.io/nefeli/mergebot:latest -f Dockerfile .
docker push ghcr.io/nefeli/mergebot:latest
