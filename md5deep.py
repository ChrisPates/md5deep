#!/usr/bin/env python
# MIT License, (c) Joshua Wright jwright@willhackforsushi.com
# https://github.com/joswr1ght/md5deep
import os, sys, hashlib, re, multiprocessing
from Queue import Queue
from threading import Thread
import time, datetime

# To stop the queue from consuming all the RAM available
MaxQueue = 1000

# Reproduce this output with slashes consistent for Windows systems
#ba2812a436909554688154be461d976c  A\SEC575-Clown-Chat\nvram

# file regex
md5FileRegex = re.compile(r'^(?P<hash>[a-f0-9]{32})  (?P<path>(/)?([^/\0]+(/)?)+)\n$')

file_queue = Queue(MaxQueue)

# Optimized for low-memory systems, read whole file with blocksize=0
def md5sum(filename, blocksize=65536):
    hash = hashlib.md5()
    with open(filename, "rb") as f:
        for block in iter(lambda: f.read(blocksize), ""):
            hash.update(block)
    return hash.hexdigest().strip()

def mod_datetime(filename):
    t = os.path.getmtime(filename)
    return datetime.datetime.fromtimestamp(t)


def usage():
    print "Usage: md5deep.py [OPTIONS] [FILES]"
    print "-r        - recursive mode, all subdirectories are traversed."
    print "-n        - During any of the matching modes (-m,-M,-x,or -X), displays only the filenames of any known hashes that were not matched by any of the input files."
    print "-M <file> - enables matching mode."
    print "-m <file> - as above."
    print "-X <file> - enables negative matching mode."
    print "-x <file> - as above."
    print "-n        - used with -MmXx so only file name outputed."
    print "-f        - speed up hash calculations, using more memory."
    print "-0        - Uses a NULL character (/0) to terminate each line instead of a newline. Useful for processing filenames with strange characters."
    print "-jnn      - Controls multi-threading. By default the program will create one producer thread to scan the file system and one hashing thread per CPU core. Multi-threading causes output filenames to be in non-deterministic order, as files that take longer to hash will be delayed while they are hashed. If a deterministic order is required, specify -j0 to disable multi-threading."
    print "-t yyyymmddThhmmss - include only files modified after the timestamp provided."

def formatOutput(hash, path):
    hash = hash.replace(" ","")
    path = path.replace("\r","")
    path = path.replace("\n","")

    if opt_nameonly:
        sys.stdout.write("%s%s"%(path,  opt_endofline))
    else:
        sys.stdout.write("%s  %s%s"%(hash, path, opt_endofline))

def validate_hashes(hashfile, hashlist, mode):
    # Open file and build a new hashlist
    hashlistrec = []
    with open(hashfile, "r") as f:
        for line in f:
            hashpair = md5FileRegex.match(line)
            if hashpair:
               filehash = hashpair.group('hash')
               filename = hashpair.group('path')
               # Convert to platform covention directory separators
               filename = normfname(hashpair.group('path'))
               # Add entry to hashlistrec
               hashlistrec.append((filename, filehash))

        if mode == "neg":
            for diff in list(set(hashlist) - set(hashlistrec)):
                formatOutput(diff[1], normfname(diff[0]))
        elif mode == "pos":
            for inter in list(set(hashlistrec) & set(hashlist)):
                formatOutput(inter[1], normfname(inter[0]))

# Normalize filename based on platform
def normfname(filename):
    if os.name == 'nt': # Windows
        return filename.replace("/", "\\")
    else:
        return filename.replace("\\","/")

# Worker thread function
def calcMD5(i, q):
    while True:
        path = q.get()
	formatOutput(md5sum(path, md5blocklen),  path)
        q.task_done()

if __name__ == '__main__':
    
    opt_recursive = None
    opt_negmatch = None
    opt_match = None
    opt_nameonly = None
    opt_hashtable = None
    opt_fast = None
    opt_endofline = "\n"
    opt_files = []
    opt_threads = multiprocessing.cpu_count()
    opt_timestamp =""

    if len(sys.argv) == 1:
        usage()
        sys.exit(0)

    args = sys.argv[1:]
    it = iter(args)
    for i in it:
        if i == '-r':
            opt_recursive = True
            continue
        elif i == '-0':
            opt_endofline = "\0\n"
            continue
        elif i == '-f':
            opt_fast = True
        elif i == '-X' or i == '-x':
            opt_negmatch = next(it)
            if not os.path.isfile(opt_negmatch):
                sys.stdout.write("Cannot open negative match file %s\n"%opt_negmatch)
                sys.exit(-1)
            continue
        elif i == '-M' or i == '-m':
            opt_match = next(it)
            if not os.path.isfile(opt_match):
                sys.stdout.write("Cannot open match file %s\n"%opt_match)
                sys.exit(-1)
            continue
        elif i == '-n' and (opt_negmatch or opt_match):
            opt_nameonly = True
            continue
        elif i.startswith('-j'):
            opt_threads = int(i[2:])
            continue
        elif i == '-t':
            opt_timestamp = datetime.datetime.strptime( next(it), "%Y%m%dT%H%M%S" )
            if not opt_timestamp:
                sys.stdout.write("Is not valid ISO timestamp %s\n"%opt_timestampe)
                sys.exit(-1)
            continue
        else:
            opt_files.append(i)

    if opt_fast:
        md5blocklen=0
    else:
        # Default to optimize for low-memory systems
        md5blocklen=65536

    # If we are not doing matching then we by-pass the hashtable
    # this saves RAM and allows us to process much larger filesystems
    if opt_negmatch or opt_match:
        opt_hashtable = True
    else:
        opt_hashtable = False

    if opt_threads:
        for i in range(opt_threads):
            worker = Thread(target=calcMD5, args=(i, file_queue))
            worker.setDaemon(True)
            worker.start()
 
    # Build a list of (hash,filename) for each file, regardless of specified 
    # options
    hashlist = []
    # Hash files in the current directory
    for f in opt_files:
        if os.path.isfile(f):
            hashlist.append((f, md5sum(f, md5blocklen)))
  
    # Walk all subdirectories
    if opt_recursive:
        for start in sys.argv[1:]:
            for (directory, _, files) in os.walk(start):
                for f in files:
                    path = os.path.join(directory, f)
                    if opt_hashtable:
                       hashlist.append((path, md5sum(path, md5blocklen)))
                    elif not opt_timestamp or (mod_datetime(path) > opt_timestamp and opt_timestamp):
                       if opt_threads:
                          # Add it to the queue
                          file_queue.put(path)     
                       else:
                          # Threading disabled
	                  formatOutput(md5sum(path, md5blocklen),  path)
                       

    # With the hashlist built, compare to the negative/posative match list, or print
    # the results.
    if opt_threads:
        file_queue.join()
    elif opt_negmatch:
        validate_hashes(opt_negmatch, hashlist, "neg")
    elif opt_match:
        validate_hashes(opt_match, hashlist, "pos")
    else:
        # Just print out the list with Windows-syle filenames
        for hash in hashlist:
           formatOutput(hash[1],normfname(hash[0]))
