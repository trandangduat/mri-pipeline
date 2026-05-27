FROM freesurfer/freesurfer:7.4.1

LABEL maintainer="Bao"
LABEL description="Base image cho FreeSurfer Stack"

RUN sed -i 's/mirrorlist/#mirrorlist/g' /etc/yum.repos.d/CentOS-* && \
    sed -i 's|#baseurl=http://mirror.centos.org|baseurl=http://vault.centos.org|g' /etc/yum.repos.d/CentOS-*

RUN yum install -y python3 python3-pip \
    && yum clean all \
    && rm -rf /var/cache/yum

ENV FREESURFER_HOME=/usr/local/freesurfer
ENV SUBJECTS_DIR=/output
ENV PATH=$FREESURFER_HOME/bin:$PATH
ENV FS_LICENSE=/license/license.txt

RUN mkdir -p /input /output /work /license /app
WORKDIR /app
