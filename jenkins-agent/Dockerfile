FROM jenkins/ssh-agent:alpine-jdk21

USER root

RUN apk add --no-cache \
    docker-cli \
    git \
    curl \
    unzip \
    jq \
    ca-certificates

# Install kubectl
RUN curl -LO "https://dl.k8s.io/release/v1.30.0/bin/linux/amd64/kubectl" \
    && chmod +x kubectl \
    && mv kubectl /usr/local/bin/kubectl
