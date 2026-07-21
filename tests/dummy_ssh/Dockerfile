FROM alpine:latest
RUN apk add --no-cache openssh python3 bash sudo
RUN ssh-keygen -A
RUN adduser -D -s /bin/bash tester && \
    echo "tester:tester" | chpasswd && \
    echo "tester ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers
RUN sed -i 's/#PasswordAuthentication yes/PasswordAuthentication yes/g' /etc/ssh/sshd_config
RUN sed -i 's/#PermitRootLogin.*/PermitRootLogin yes/g' /etc/ssh/sshd_config
# Create a dummy workspace folder for testing
RUN mkdir -p /home/tester/mri_workspace/job_123 && \
    touch /home/tester/mri_workspace/job_123/dummy.txt && \
    chown -R tester:tester /home/tester/mri_workspace
CMD ["/usr/sbin/sshd", "-D"]
