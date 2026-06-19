FROM freesurfer/freesurfer:8.0.0

RUN sed -i 's/mirrorlist/#mirrorlist/g' /etc/yum.repos.d/CentOS-* 2>/dev/null || true && \
    sed -i 's|#baseurl=http://mirror.centos.org|baseurl=http://vault.centos.org|g' /etc/yum.repos.d/CentOS-* 2>/dev/null || true

RUN yum install -y python3 python3-pip \
    && yum clean all \
    && rm -rf /var/cache/yum

ENV FREESURFER_HOME=/usr/local/freesurfer/8.0.0-1
ENV SUBJECTS_DIR=/output
ENV PATH=$FREESURFER_HOME/bin:$PATH
ENV FS_LICENSE=/license/license.txt

RUN mkdir -p /input /output /work /license /app
WORKDIR /app
