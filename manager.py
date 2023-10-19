#!/usr/bin/env python
import pika, sys, os, json, subprocess, time, docker
from minio import Minio
from minio.error import S3Error
from subprocess import Popen, PIPE, CalledProcessError
from datetime import datetime

from queue import Empty, Queue
from threading import Thread

class Manager:

    def __init__(self):
        self.shutdown = False
        
        # Create a client with the MinIO server playground, its access key
        # and secret key.
        s3Host = os.getenv('MINIO_HOST')
        s3Access = os.getenv('MINIO_ACCESS_KEY')
        s3Secret = os.getenv('MINIO_SECRET_KEY')
        s3Secure = os.getenv('MINIO_SECURE')

        if not s3Host or not s3Access or not s3Secret:
            print(" [*] Upscaler missing s3 host or access or secret or all")
            try:
                sys.exit(0)
            except SystemExit:
                os._exit(0)     

        if not s3Secure:
            s3Secure = False

        self.s3Client = Minio(
            s3Host,
            access_key=s3Access,
            secret_key=s3Secret, 
            secure=s3Secure
        )

        # RabbitMQ
        mqHost = os.getenv('MQ_HOST')
        mqAccess = os.getenv('MQ_ACCESS')
        mqSecret = os.getenv('MQ_SECRET')
        mqPort = os.getenv('MQ_PORT')

        if not mqHost or not mqAccess or not mqSecret:
            print(" [*] Upscaler missing mq host or access or secret or all")
            try:
                sys.exit(0)
            except SystemExit:
                os._exit(0)     

        if not mqPort:
            mqPort = 5672

        self.mqCredentials = pika.PlainCredentials(mqAccess, mqSecret)
        self.mqParameters = pika.ConnectionParameters(host=mqHost, port=mqPort, virtual_host='/', credentials=self.mqCredentials)
        
        self.mqConnection = pika.BlockingConnection(self.mqParameters)
        self.mqChannel = self.mqConnection.channel()

        # Docker client
        self.dockerClient = docker.from_env()


    # Here we define the main script that will be executed forever until a keyboard interrupt exception is received
    def start(self):

        print("Manager starting...")
        found = self.s3Client.bucket_exists("incoming")
        if found:
            print("Bucket 'incoming' exists")

        found = self.s3Client.bucket_exists("outgoing")
        if found:
            print("Bucket 'outgoing' exists")

        def execute(self, command):
            subprocess.check_call(command, shell=True, stdout=sys.stdout, stderr=subprocess.STDOUT)

        # Consume a message from a queue. The auto_ack option simplifies our example, 
        # as we do not need to send back an acknowledgement query to RabbitMQ 
        # which we would normally want in production
        self.mqChannel.basic_consume(queue='incoming_queue', on_message_callback=self.callback, auto_ack=True)
        print(' [*] Manager waiting for messages...')
        
        # Start listening for messages to consume
        self.mqChannel.start_consuming()
        
    # Since RabbitMQ works asynchronously, every time you receive a message, a callback function is called. We will simply print the message body to the terminal 
    def callback(self, ch, method, properties, body):
        if not manager.shutdown:
        
            #print(" [x] Received %r" % body)
            message = json.loads(body.decode('utf-8'))
            key = message['Records'][0]['s3']['object']['key']
            contentType = message['Records'][0]['s3']['object']['contentType']
            eventType = message['EventName']
            #if ":Put" in eventType:
            print(" [x] Event %r" % eventType) 
            print(" [x] Key %r" % key) 
            print(" [x] Type %r" % contentType) 
            upscaled = key.split(".",1)[0] + "_upscaled.png"
            if contentType == "image/jpeg" or contentType == "image/png" or contentType == "application/octet-stream":
                upscaler = self.dockerClient.containers.run(
                     "upscaler", command="python3 upscaler.py", name=key+datetime.now().strftime('-%Y%m-%d%H-%M%S'), 
                     mem_limit="4GB", network="upscaler_net", 
                     environment=["JSON="+ json.dumps(message), "IMAGE="+key, "CONTENTTYPE="+contentType], 
                     detach=True)
                print(upscaler.logs())


    def exit_gracefully(self, signum, frame): 
        print('[*] Manager received:', signum) 

        self.mqChannel.stop_consuming()
        del self.mqChannel
        del self.s3Client

        for container in self.dockerClient.containers.list(filters={'ancestor': 'upscaler'}):
            print('[*] Manager stopping ' + container.name)
            container.kill()

        del self.dockerClient

    def run(self):
        print("[*] Manager running ...")
        time.sleep(1)

    def stop(self): 
        print("[*] Manager stopping...")

if __name__ == '__main__':
    
    manager = Manager();
    try:
        manager.start()
    except KeyboardInterrupt:
        print("[*] Manager Interrupted")
        manager.exit_gracefully(manager, frame=False)
        sys.exit(0)
    