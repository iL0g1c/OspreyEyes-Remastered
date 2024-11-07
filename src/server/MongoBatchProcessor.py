from pymongo import MongoClient, UpdateOne
import time
import logging
import sys

class MongoBatchProcessor:
    def __init__(self, collection, batch_size=50, interval=5):
        self.logger = logging.getLogger("MongoBatchProcessor")
        self.logger.setLevel(logging.DEBUG)
        self.logger.addHandler(logging.StreamHandler(sys.stdout))

        self.collection = collection
        self.batch_size = batch_size
        self.interval = interval
        self.batch = []
        self.last_flush_time = time.time()
    def add_to_batch(self, update):
        self.batch.append(update)
        if len(self.batch) >= self.batch_size or time.time() - self.last_flush_time >= self.interval:
            self.flush_batch()
    def flush_batch(self):
        if self.batch:
            try:
                self.collection.bulk_write(self.batch, ordered=False)
            except Exception as e:
                self.logger.log(40, f"Error flushing batch to MongoDB: {e}")
            finally:
                self.batch = []
                self.last_flush_time = time.time()
