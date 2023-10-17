FROM ubuntu:latest

RUN apt-get update
RUN apt-get install openssh-server unzip -y

RUN mkdir /var/run/sshd

RUN echo 'root:pwd' | chpasswd

# SSH allow root login via remote
RUN sed -i 's/#PermitRootLogin/PermitRootLogin/g' /etc/ssh/sshd_config

# SSH login fix. Otherwise user is kicked off after login
RUN sed 's@session\s*required\s*pam_loginuid.so@session optional pam_loginuid.so@g' -i /etc/pam.d/sshd

# RESTART SSH
RUN /etc/init.d/ssh restart

# Add ubuntu upscaler
COPY main.py main.py

# Start main script
RUN apt-get install python3 pip -y
RUN pip install pika
RUN pip install minio
RUN pip install pillow
RUN pip install docker
ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python3", "main.py"]

