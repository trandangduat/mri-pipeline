FROM vnmd/cat12_26.0.rc3:latest AS source

FROM ubuntu:22.04

LABEL description="CAT12 26.0.rc3 standalone rebased on Ubuntu 22.04 for GLIBC 2.35"

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash ca-certificates coreutils findutils grep sed gawk file procps unzip \
    python3 python3-nibabel \
    libc6 libgcc-s1 libstdc++6 libgomp1 zlib1g \
    libx11-6 libxext6 libxmu6 libxt6 libxrender1 libxrandr2 libxi6 \
    libxinerama1 libxcursor1 libxcomposite1 libxdamage1 libxfixes3 \
    libasound2 libatk1.0-0 libatk-bridge2.0-0 libgtk2.0-0 libgtk-3-0 \
    libglib2.0-0 libglu1-mesa libgl1 libncurses5 libnss3 libxss1 \
    libfontconfig1 libfreetype6 libdbus-1-3 libexpat1 libxcb1 libxau6 \
    libxdmcp6 libuuid1 libsm6 libice6 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=source /opt/cat12 /opt/cat12
COPY --from=source /opt/mcr /opt/mcr

ENV PATH=/opt/cat12:/opt/cat12/standalone:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
ENV SPMROOT=/opt/cat12
ENV MCRROOT=/opt/mcr/R2023b

ENTRYPOINT ["/opt/cat12/standalone/cat_standalone.sh"]
