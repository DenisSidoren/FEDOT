import logging
import logging.handlers
import os
import multiprocessing

from fedot.core.log import default_log
from fedot.core.utils import default_fedot_data_dir

log = default_log('test')


def logging_func(msg):
    log.message(msg)


def worker_init(q):
    qh = logging.handlers.QueueHandler(q)
    logger2 = logging.getLogger()
    logger2.setLevel(logging.DEBUG)
    logger2.addHandler(qh)


def multiproc_wrapper():

    queue = multiprocessing.Queue()

    file_handler = logging.handlers.RotatingFileHandler(os.path.join(default_fedot_data_dir(), 'log.log'))
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    file_handler.setLevel(logging.DEBUG)

    queue_listener = logging.handlers.QueueListener(queue, file_handler)
    queue_listener.start()
    return queue


if __name__ == '__main__':
    # In case we will initialize the queue and listener before parallelization
    msgs = [i for i in range(1000)]
    with multiprocessing.Pool(3, worker_init, [multiproc_wrapper()]) as pool:
        list(pool.imap_unordered(logging_func, msgs))

    if os.path.exists(os.path.join(default_fedot_data_dir(), 'log.log')):
        with open(os.path.join(default_fedot_data_dir(), 'log.log'), 'r') as file:
            content = file.readlines()

    if len(content) == len(msgs):
        print('successfully')
    print(len(content))

    content = ''.join(i for i in content)

    for i in msgs:
        if str(i) not in content:
            print(f'{i} NOT IN LOGS')



