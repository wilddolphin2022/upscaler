#!/usr/bin/env python
import pika, sys, os, json, subprocess, time, docker
from minio import Minio
from minio.error import S3Error
from subprocess import Popen, PIPE, CalledProcessError
from PIL import Image

from queue import Empty, Queue
from threading import Thread

Image.MAX_IMAGE_PIXELS = None

_BAR_SIZE = 20
_KILOBYTE = 1024
_FINISHED_BAR = '#'
_REMAINING_BAR = '-'

_UNKNOWN_SIZE = '?'
_STR_MEGABYTE = ' MB'

_HOURS_OF_ELAPSED = '%d:%02d:%02d'
_MINUTES_OF_ELAPSED = '%02d:%02d'

_RATE_FORMAT = '%5.2f'
_PERCENTAGE_FORMAT = '%3d%%'
_HUMANINZED_FORMAT = '%0.2f'

_DISPLAY_FORMAT = '|%s| %s/%s %s [elapsed: %s left: %s, %s MB/sec]'

_REFRESH_CHAR = '\r'

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

    # Upload '/home/user/Photos/asiaphotos.zip' as object name
    # 'asiaphotos-2015.zip' to bucket 'asiatrip'.
    #client.fput_object(
    #    "incoming", "input.jpg", "input.jpg",
    #)
    #print(
    #    "'main.py' is successfully uploaded as "
    #    "object 'main.py' to bucket 'incoming'."
    #)

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
            client.containers.run("upscaler", key, detach=True)
                # Ze processing loop
                # client.fget_object(
                #     "incoming", key, key)
                # img = Image.open(key)
                # size = img.size;
                # img.close()
                # model = "-n ultrasharp" 
                # args = "./realesrgan-ncnn-vulkan -i {k} -o {u} {n}".format(k=key, u=upscaled, n=model)
                # execute([args])
                # img = Image.open(upscaled)
                # img = img.resize((size[0], size[1]), Image.Resampling.LANCZOS)
                # #new_img = img.crop((0, 0, size[0] /2, size[1] /2))
                # img.save(upscaled, quality=100, optimize=True)
                # #new_img.close()
                # img.close()
                # client.fput_object(
                #     "outgoing", upscaled, upscaled, progress=Progress())


    # Consume a message from a queue. The auto_ack option simplifies our example, 
    # as we do not need to send back an acknowledgement query to RabbitMQ 
    # which we would normally want in production
    channel.basic_consume(queue='incoming_queue', on_message_callback=callback, auto_ack=True)
    print(' [*] Waiting for messages. To exit press CTRL+C')
    

    # Start listening for messages to consume
    channel.start_consuming()
    
class Progress(Thread):
    """
        Constructs a :class:`Progress` object.
        :param interval: Sets the time interval to be displayed on the screen.
        :param stdout: Sets the standard output
        :return: :class:`Progress` object
    """

    def __init__(self, interval=1, stdout=sys.stdout):
        Thread.__init__(self)
        self.daemon = True
        self.total_length = 0
        self.interval = interval
        self.object_name = None

        self.last_printed_len = 0
        self.current_size = 0

        self.display_queue = Queue()
        self.initial_time = time.time()
        self.stdout = stdout
        self.start()

    def set_meta(self, total_length, object_name):
        """
        Metadata settings for the object. This method called before uploading
        object
        :param total_length: Total length of object.
        :param object_name: Object name to be showed.
        """
        self.total_length = total_length
        self.object_name = object_name
        self.prefix = self.object_name + ': ' if self.object_name else ''

    def run(self):
        displayed_time = 0
        while True:
            try:
                # display every interval secs
                task = self.display_queue.get(timeout=self.interval)
            except Empty:
                elapsed_time = time.time() - self.initial_time
                if elapsed_time > displayed_time:
                    displayed_time = elapsed_time
                self.print_status(current_size=self.current_size,
                                  total_length=self.total_length,
                                  displayed_time=displayed_time,
                                  prefix=self.prefix)
                continue

            current_size, total_length = task
            displayed_time = time.time() - self.initial_time
            self.print_status(current_size=current_size,
                              total_length=total_length,
                              displayed_time=displayed_time,
                              prefix=self.prefix)
            self.display_queue.task_done()
            if current_size == total_length:
                self.done_progress()

    def update(self, size):
        """
        Update object size to be showed. This method called while uploading
        :param size: Object size to be showed. The object size should be in
                     bytes.
        """
        if not isinstance(size, int):
            raise ValueError('{} type can not be displayed. '
                             'Please change it to Int.'.format(type(size)))

        self.current_size += size
        self.display_queue.put((self.current_size, self.total_length))

    def done_progress(self):
        self.total_length = 0
        self.object_name = None
        self.last_printed_len = 0
        self.current_size = 0

    def print_status(self, current_size, total_length, displayed_time, prefix):
        formatted_str = prefix + format_string(current_size, total_length, displayed_time)
        self.stdout.write(_REFRESH_CHAR + formatted_str + ' ' *
                        max(self.last_printed_len - len(formatted_str), 0))
        self.stdout.flush()
        self.last_printed_len = len(formatted_str)

def seconds_to_time(seconds):
    """
    Consistent time format to be displayed on the elapsed time in screen.
    :param seconds: seconds
    """
    minutes, seconds = divmod(int(seconds), 60)
    hours, m = divmod(minutes, 60)
    if hours:
        return _HOURS_OF_ELAPSED % (hours, m, seconds)
    else:
        return _MINUTES_OF_ELAPSED % (m, seconds)


def format_string(current_size, total_length, elapsed_time):
    """
    Consistent format to be displayed on the screen.
    :param current_size: Number of finished object size
    :param total_length: Total object size
    :param elapsed_time: number of seconds passed since start
    """

    n_to_mb = current_size / _KILOBYTE / _KILOBYTE
    elapsed_str = seconds_to_time(elapsed_time)

    rate = _RATE_FORMAT % (
        n_to_mb / elapsed_time) if elapsed_time else _UNKNOWN_SIZE
    
    if total_length > 0:
        frac = float(current_size) / total_length
    else:
        frac = 0
        print("\n")
        sys.exit()

    bar_length = int(frac * _BAR_SIZE)
    bar = (_FINISHED_BAR * bar_length +
           _REMAINING_BAR * (_BAR_SIZE - bar_length))
    percentage = _PERCENTAGE_FORMAT % (frac * 100)

    left_str = (
        seconds_to_time(
            elapsed_time / current_size * (total_length - current_size))
        if current_size else _UNKNOWN_SIZE)

    humanized_total = _HUMANINZED_FORMAT % (
        total_length / _KILOBYTE / _KILOBYTE) + _STR_MEGABYTE
    humanized_n = _HUMANINZED_FORMAT % n_to_mb + _STR_MEGABYTE

    return _DISPLAY_FORMAT % (bar, humanized_n, humanized_total, percentage,
                              elapsed_str, left_str, rate)



if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("Interrupted")
        try:
            sys.exit(0)
        except SystemExit:
            os._exit(0)
