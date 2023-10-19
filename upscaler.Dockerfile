#FROM ubuntu:latest
FROM nvidia/cuda:12.2.0-base-ubuntu22.04

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
COPY realesrgan-ncnn-vulkan-20220424-ubuntu.zip realesrgan-ncnn-vulkan-20220424-ubuntu.zip
COPY upscaler.py upscaler.py
RUN apt-get install gcc libvulkan-dev -y
RUN unzip realesrgan-ncnn-vulkan-20220424-ubuntu.zip
RUN rm realesrgan-ncnn-vulkan-20220424-ubuntu.zip
RUN chmod +x realesrgan-ncnn-vulkan
COPY models models

# Start main script
RUN apt-get install python3 pip -y
RUN pip install pika
RUN pip install minio
RUN pip install pillow
#RUN pip install runpod
ENV PYTHONUNBUFFERED=1

#ENTRYPOINT ["python3", "upscaler.py"]

