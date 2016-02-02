#!/usr/bin/env python
# encoding: utf-8

import subprocess
import os
from datetime import datetime
import time

def get_output(*command):
    p = subprocess.Popen(command, stdout=subprocess.PIPE)
    (stdout, stderr) = p.communicate()
    return stdout

def pretty_number(num):
    scales = ['', 'K', 'M', 'G', 'T', 'P', 'E']
    for scale in scales:
        if num < 1024:
            return "%8d%s" % (num,scale)
        num = int(num / 1024)

class ZIOStat(object):

    def __init__(self):
        self.diskmap = {}
        self.get_disks()
        self.data = {}
        self.previous = None
        self.sector_cache = {}

    def get_disks(self):
        # Todo: replace with os.walk
        disks = get_output("find", "/dev/zvol/", "-type", "l")
        disks = disks.splitlines()
        maps = {}
        for disk in disks:
            device = os.readlink(disk)
            device = device.split('/')[-1]
            if device[-2] == 'p' and device[-1].isdigit():
                continue
            maps[device] = disk[10:]
        self.diskmap = maps

    def get_sector_size(self, device):
        if device not in self.sector_cache:
            with open('/sys/block/%s/queue/hw_sector_size' % device) as f:
                val = int(f.read().strip())
                self.sector_cache[device] = val
        return self.sector_cache[device]

    def get_diskstats(self):
        newdata = {}
        interval = 0
        total = {}
        now = datetime.now()
        if self.previous:
            interval = (now - self.previous).total_seconds()
        self.previous = now
        with open('/proc/diskstats') as f:
            for line in f.readlines():
                data = dict(zip(["major", "minor", "name", "reads_completed", "reads_merged", "read_sectors", "reads_total_time", "writes_completed", "writes_merged", "write_sectors", "writes_total_time", "io_pending", "io_total_time", "io_weighted_time"],line.strip().split()))
                if data["name"] not in self.diskmap:
                    continue

                for field in data.keys():
                    if field == 'name':
                        continue
                    data[field] = int(data[field])

                data['zvol'] = self.diskmap[data["name"]]
                data['read_bytes'] = data['read_sectors'] * self.get_sector_size(data["name"])
                data['write_bytes'] = data['write_sectors'] * self.get_sector_size(data["name"])
                newdata[data["name"]] = data
        if not self.data:
            self.data = newdata
            return {}
        out = {}
        for device in newdata:
            if device not in self.data:
                continue
            out[device] = {}
            for field in newdata[device].keys():
                if field in ['major', 'minor', 'name', 'zvol', 'io_pending', 'io_total_time', 'io_weighted_time', 'writes_total_time', 'reads_total_time']:
                    val = newdata[device][field]
                else:
                    val = (newdata[device][field] - self.data[device][field]) / interval
                    if field not in total:
                        total[field] = 0
                    total[field] += val
                out[device][field] = val
        total['zvol'] = 'total'
        out["total"] = total
        self.data = newdata
        return out

if __name__ == '__main__':
    z = ZIOStat()
    while True:
        print("%(zvol)60s %(reads_completed)8s %(writes_completed)8s %(read_bytes)12s %(write_bytes)12s" % {"zvol": "device", "reads_completed": "read ops", "writes_completed": "write ops", "read_bytes": "read B/s", "write_bytes": "write B/s"})
        stats = z.get_diskstats()
        for device in sorted(stats.keys()):
            #if device == 'total':
            #    continue
            line = dict(stats[device])
            line["write_percent"] = 0
            line["read_percent"] = 0
            if stats['total']['write_bytes']:
                line["write_percent"] = (100.0 * line["write_bytes"]) / stats['total']['write_bytes']
            if stats['total']['read_bytes']:
                line["read_percent"] = (100.0 * line["read_bytes"]) / stats['total']['read_bytes']
            line["zvol"] = line["zvol"].ljust(60)

            for k in ['reads_completed', 'writes_completed', 'read_bytes', 'write_bytes']:
                line[k] = pretty_number(line[k])
            print("%(zvol)60s %(reads_completed)8s %(writes_completed)8s %(read_bytes)12s %(write_bytes)12s %(read_percent)6.2f%% %(write_percent)6.2f%%" % line)
        time.sleep(1)
        print("----")
