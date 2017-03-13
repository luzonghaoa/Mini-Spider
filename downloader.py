import os
import sys
import time
import socket
import ftplib

import urllib.parse
import urllib.request

from ssl import _create_unverified_context


class Downloader:
    """This class is used to handle the Download requests that arrive at the server."""

    def __init__(self, url, filename='', work_path='', block_size=1024 * 1024, headers={}, timeout=2, ssl_context=None,
                 terminal_mode=False, url_check=True, ftp_user='', ftp_password=''):
        # Parse chinese to ascii and delete parameters.
        self.url = url
        self.url_check = url_check
        self._check_url()
        # If filename is not specified,it is equal to the default value provided by url.
        if filename == '':
            filename = self.url.split('/')[-1]
        # Check work directory.
        self.work_path = work_path
        self._check_work_path()
        # Check headers if not exist.
        self.headers = headers
        self._check_headers()
        # Create ssl context.
        if ssl_context:
            self.ssl_context = ssl_context
        else:
            self.ssl_context = _create_unverified_context()
        # Determine whether terminal or not.
        self.terminal_mode = terminal_mode
        # Ftp username and password.
        self.ftp_user = ftp_user
        self.ftp_password = ftp_password
        # Initialization parameters.
        self.filename = filename
        self.log_filename = self.work_path + self.filename + '._temp_log'
        self.block_size = int(block_size)
        self.block_list = []
        self.timeout = timeout
        self.content_length_now = 0
        self.content_length_size = 0
        # File Info.
        self.info = {}
        self.file_type = 'Unknown'
        self.server_code = 0
        # Progress speed.
        self._now_time = 0
        self._speed_pre_second = 0
        # Error detect
        self._error_timer = 0

    def download(self):
        if self.url.split('://')[0] == 'ftp':
            self.ftp_download()
        elif self.url.split('://')[0] == 'http' or 'https':
            self.http_download()
        else:
            print('Unknown protocol!')

    def get_server_info(self):
        req = urllib.request.Request(self.url)
        if self.headers:
            for k, v in self.headers.items():
                req.add_header(k, v)

        # Add header to tell the server where to start.
        req.add_header('Range', 'bytes=0-1')

        with urllib.request.urlopen(req, context=self.ssl_context, timeout=self.timeout) as f:
            for k, v in f.getheaders():
                # Save info.
                self.info[k] = v
                # Save important info.
                if k == 'Content-Range':
                    self.content_length_size = int(v.split('/')[-1])
                if k == 'Content-Type':
                    self.file_type = v
            # Save server code.
            self.server_code = f.getcode()

    def http_download(self):
        self.get_server_info()
        # If file is completed, pass.
        if self._check_file():
            print('%s is already completed!' % self.filename)
            return True
        # If server support resume function.
        if self._support_resume() and self.info['Content-Length'] == 2 or '2':
            # Create block list.
            self._create_block_list()
            # Check log file.
            self._log_check()
            # Start download.
            for start, end in self.block_list:
                # Ignore downloaded parts.
                if start < self.content_length_now:
                    continue
                # Try download.
                self._now_time = time.time()
                self._log_save(start)
                self._download(start, end)
                # Update progress.
                self.content_length_now = end
                self._log_save(self.content_length_now)
                # Print progress.
                self._progress_bar()
            # Delete log file
            if self.content_length_now == self.content_length_size:
                self._download_success()
                self._log_delete()
        else:
            self._download(self.content_length_now, self.content_length_size)

    def ftp_download(self):
        # Extract ip address and host.
        host = self.url.split('://')[1].split('/')[0]
        ip = socket.getaddrinfo(host=host, port='21')[0][4][0]
        # Get filename and directory.
        filename = self.url.split('://')[1].split('/')[-1]
        if self.filename == '':
            self.filename = filename
        directory = self.url.split('://')[1].split('/', 1)[1].split(filename, 1)[0]
        # Begin retrieve.
        if self.ftp_user == '' and self.ftp_password == '':
            # Simple way.
            self._now_time = time.time()
            ftp = urllib.request.URLopener()
            ftp.retrieve(url, self.work_path + self.filename, reporthook=self._ftp_progress)
        else:
            # If ftp serve need user and password.
            with ftplib.FTP(host=ip, user=self.ftp_user, passwd=self.ftp_password) as ftp:
                with open(self.work_path + self.filename, mode='ab+', buffering=self.block_size) as f:
                    ftp.login()
                    ftp.cwd('%s' % directory)
                    ftp.retrbinary('RETR %s' % filename, f.write, blocksize=self.block_size)
            self._download_success()

    def _check_headers(self):
        _headers_chrome = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_6) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/56.0.2924.87 Safari/537.36'
        }
        if self.headers == {}:
            self.headers = _headers_chrome

    def _log_save(self, content_length):
        content = [content_length]
        file = open(self.log_filename, mode='w')
        for index, item in enumerate(content):
            file.write(str(content[index]) + '\n')
        file.close()

    def _log_read(self):
        result = []

        with open(self.log_filename, 'r') as content:
            for line in content:
                if line[-1] == '\n':
                    line = line[0:-1]
                result.append(line)

        return result[0]

    def _log_delete(self):
        os.remove(self.log_filename)

    def _log_check(self):
        if os.path.isfile(self.log_filename):
            self.content_length_now = int(self._log_read())
        else:
            self._log_save(0)

    def _error(self):
        self._error_timer += 1
        if self._error_timer == 5:
            self._error_timer = 0
            time.sleep(1)

    def _download_success(self):
        # Delete redundant character.
        if self.terminal_mode:
            sys.stdout.write('                                                                        \r')
            sys.stdout.flush()
        print('%s completed' % self.filename)

    def _support_resume(self):
        if self.server_code == 0:
            self.get_server_info()
        if self.server_code == 206:
            return True
        else:
            return False

    def _create_block_list(self):
        # Attention: request length is closed interval,but python array is different.
        block_number = int((self.content_length_size - self.content_length_now) / self.block_size) + 1
        l = [x * self.block_size for x in range(0, block_number)]
        if l[-1] > self.content_length_size:
            l[-1] = self.content_length_size + 1
        else:
            l.append(self.content_length_size)
        for i in range(1, len(l)):
            temp = [l[i - 1], l[i]]
            self.block_list.append(tuple(temp))

    def _progress_bar(self):
        if self.content_length_size == 0:
            return False
        progress = (self.content_length_now / self.content_length_size)
        size_mb = self.content_length_size / (1024 * 1024)
        _time = (time.time() - self._now_time)
        self._speed_pre_second = int(self.block_size) / (_time * 1024 * 1024)
        # Print in terminal or python interpreter.
        if self.terminal_mode:
            s_terminal = 'All:%.2f mb,%.2f%% , speed: %.2fmb/s \r' % (size_mb, progress * 100, self._speed_pre_second)
            sys.stdout.write(s_terminal)
            sys.stdout.flush()
        else:
            s = 'All:%.2f mb,%.2f%% , speed: %.2fmb/s' % (size_mb, progress * 100, self._speed_pre_second)
            print(s)

    def _download(self, begin, end):
        req = urllib.request.Request(self.url)
        if self.headers:
            for k, v in self.headers.items():
                req.add_header(k, v)
        byte_range = 'bytes=' + str(begin) + '-' + str(end - 1)
        req.add_header('Range', byte_range)
        with urllib.request.urlopen(req, context=self.ssl_context, timeout=self.timeout) as r:
            with open(self.work_path + self.filename, mode='ab+', buffering=self.block_size) as f:
                f.seek(self.content_length_now)
                f.truncate()
                f.write(r.read())

    def _ftp_progress(self, _chunk_num, _chunk_size, _file_size):
        self.block_size = _chunk_size
        self.content_length_now = _chunk_num * _chunk_size
        self.content_length_size = _file_size
        if self.content_length_now > self.content_length_size:
            self.content_length_now = self.content_length_size
            self._download_success()
        else:
            self._progress_bar()
        self._now_time = time.time()

    def _check_file(self):
        try:
            file_size = os.path.getsize(self.work_path + self.filename)
            if file_size == self.content_length_size:
                return True
            else:
                return False
        except FileNotFoundError:
            return False

    def _check_work_path(self):
        try:
            os.chdir(self.work_path)
        except FileNotFoundError:
            os.mkdir(self.work_path)
        if self.work_path[-1] != '/':
            self.work_path = self.work_path + '/'

    def _check_url(self):
        # Delete get parameters.
        if self.url_check:
            self.url = self.url.split('?', 1)[0]
        # Parse chinese to ascii.
        self.url = urllib.parse.quote(self.url, safe='/:?=@&[]')


if __name__ == "__main__":
    url = 'http://www.dy2018.com/i/96869.html'
    url = 'http://www.cau.edu.cn/picture/0/1612102242504268107.jpg'
    # url = 'http://tug.org/cgi-bin/mactex-download/MacTeX.pkg'
    # url = 'https://download.jetbrains.8686c.com/idea/ideaIU-2016.3.2.dmg'
    # url = 'ftp://ftp.cau.edu.cn/Upload/FOR_MAC/Programming/RStudio-0.98.1091.dmg'
    # url = 'ftp://8:8@xia.dl1234.com:8807/[电影天堂www.dy2018.com]美国队长3DVD中英双字.rmvb'
    url = 'http://pt.cau.edu.cn/download.php?tid=155042'

    a = Downloader(url,
                   work_path='/Users/zyh/github/Mini-Spider/test',
                   block_size=1024 * 1024 * 10,
                   terminal_mode=False,
                   url_check=False
                   )
    a.download()
