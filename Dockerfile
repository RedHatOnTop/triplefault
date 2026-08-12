# TripleFault v1 -- pinned so scores are comparable across submitters.
FROM ubuntu:24.04

RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential gcc-multilib \
      qemu-system-x86 \
      python3 git make \
    && rm -rf /var/lib/apt/lists/*

# Record the exact versions in every result. QEMU minor versions change
# fault timing; a score is only comparable against the same row.
RUN qemu-system-i386 --version | head -1 > /etc/tf-versions \
 && gcc --version | head -1 >> /etc/tf-versions

WORKDIR /work
COPY . /work
RUN make

CMD ["python3", "harness/score.py"]
