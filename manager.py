#!/usr/bin/env python
import pika, sys, os, json, subprocess, time, docker
from minio import Minio
from minio.error import S3Error
from subprocess import Popen, PIPE, CalledProcessError

from queue import Empty, Queue
from threading import Thread

# Here we define the main script that will be executed forever until a keyboard interrupt exception is received
def main():

    # Create a client with the MinIO server playground, its access key
    # and secret key.
    client = Minio(
        "minio:9000",
        access_key="minio",
        secret_key="miniosecretkey", 
        secure=False
    )

    found = client.bucket_exists("incoming")
    if found:
        print("Bucket 'incoming' exists")

    found = client.bucket_exists("outgoing")
    if found:
        print("Bucket 'outgoing' exists")

    credentials = pika.PlainCredentials('guest', 'guest')
    parameters = pika.ConnectionParameters(host='rabbitmq', port=5672, virtual_host='/', credentials=credentials)
    
    connection = pika.BlockingConnection(parameters)
    channel = connection.channel()
    #channel.queue_declare(queue='incoming_queue', passive=False, durable=True)

    def execute(command):
        subprocess.check_call(command, shell=True, stdout=sys.stdout, stderr=subprocess.STDOUT)

    # Since RabbitMQ works asynchronously, every time you receive a message, a callback function is called. We will simply print the message body to the terminal 
    def callback(ch, method, properties, body):
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
            client = docker.from_env()
            container = client.containers.run("upscaler", command="printenv", network="upscaler_net", environment=["IMAGE="+key, "CONTENTTYPE="+contentType], detach=True)

    # Consume a message from a queue. The auto_ack option simplifies our example, 
    # as we do not need to send back an acknowledgement query to RabbitMQ 
    # which we would normally want in production
    channel.basic_consume(queue='incoming_queue', on_message_callback=callback, auto_ack=True)
    print(' [*] Waiting for messages. To exit press CTRL+C')
    

    # Start listening for messages to consume
    channel.start_consuming()
    
if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("Interrupted")
        try:
            sys.exit(0)
        except SystemExit:
            os._exit(0)
