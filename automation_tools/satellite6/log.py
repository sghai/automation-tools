# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from itertools import cycle

import os
import re
from fabric.api import execute, run

ERROR_TOKENS = (
    'ERROR',
    'EXCEPTION',
    r'returned 1 instead of one of \[0\]',
    'Could not find the inverse association for repository',
    'undefined method'
)

LOG_FILES = (
    '/var/log/foreman-installer/satellite.log',
    '/var/log/satellite-installer/satellite-installer.log',
    '/var/log/capsule-installer/capsule-installer.log',
    '/var/log/foreman-installer/capsule.log',
    '/var/log/foreman/production.log',
    '/var/log/foreman-proxy/proxy.log',
    '/var/log/candlepin/candlepin.log',
    '/var/log/messages',
    '/var/log/mongodb/mongodb.log',
    '/var/log/tomcat/catalina.out'
)


class LogAnalyzer(object):
    """Context Manager to analyze changes in logs during some process.
    Example:

    >>> from automation_tools.satellite6.log import LogAnalyzer
    >>> with LogAnalyzer('root@sathost.redhat.com'):
    ...     print('Running some process, could be Satellite Upgrade')
    ...
    [root@sathost.redhat.com] Executing task 'get_line_count'
    Running some process, could be Satellite Upgrade
    #### Analyzing logs of host root@sathost.redhat.com
    [root@sathost.redhat.com] Executing task 'get_line_count'
    [root@sathost.redhat.com] Executing task 'fetch_appended_log_lines'

    """

    def __init__(self, host):
        """Initializes context manager with Satellite hostname

        :param host: str the hostname
        """
        self.host = host
        self.log_state = dict(zip(LOG_FILES, cycle([0])))

    def __enter__(self):
        """
        Fetch current line count for Satellite log files
        :return: LogAnalyzer
        """
        self._update_log_files_state()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Analyzes log files checking if some error occurred since last
        log_state update
        """
        print('#### Analyzing logs of host %s' % self.host)
        self._update_log_files_state()

        def fetch_appended_log_lines():
            for log_file, lines_appended in self.log_state.items():
                if lines_appended > 0:
                    content = run(
                        'tail -n {} {}'.format(lines_appended, log_file),
                        quiet=True
                    )
                    analyze(self.host, log_file, content)

        execute(fetch_appended_log_lines, host=self.host)

    def _update_log_files_state(self):
        """Update log_dct with adding delta from current number of lines of
        each item and the last provided by dct.

        So this method can be used to check how many lines were appended on
        a file during some processes and used to tail them. If log_state is
        None a new dict is created with initial values been 0 (zero).
        """

        def get_line_count():
            for log_file, old_value in self.log_state.items():
                try:
                    current_value = int(
                        run(
                            'wc -l < {}'.format(log_file),
                            quiet=True
                        )
                    )
                except ValueError:
                    self.log_state[log_file] = 0
                else:
                    self.log_state[log_file] = current_value - old_value

        execute(get_line_count, host=self.host)


def _save_full_log(host, log_file_path, content):
    """Save full log on upgrade-diff-logs dir

    :param host: str with host name
    :param log_file_path: file name path
    :param content: content to be saved
    """
    dir_path = os.path.abspath('upgrade-diff-logs')
    if not os.path.exists(dir_path):
        os.mkdir(dir_path)
    log_file_name = os.path.split(log_file_path)[-1]
    log_file_name = '%s-%s' % (host, log_file_name)
    file_path = os.path.join(dir_path, log_file_name)
    with open(file_path, 'wb') as log_file:
        log_file.write(content)
        _print_wrapper('## Full upgrade logs saved on %s' % file_path)


def analyze(host, log_file, content):
    """Analyzes appended content from a log file. For now it is only
    checking for ERROR status on regular log files.

    :param host: str with host name
    :param log_file: str log file path on host
    :param content: str with log file content
    """

    def print_lines(lines_enumeration):
        """print lines with numbers"""
        no_line_flag = True
        for i, line in lines_enumeration:
            _print_wrapper('{}: {}'.format(i, line))
            no_line_flag = False
        if no_line_flag:
            _print_wrapper('No errors found')

    _print_wrapper('### Analyzing %s:' % log_file)
    _print_wrapper('## Errors found:')
    content_lines = content.decode('utf-8').split('\n')
    regex = '|'.join(map(lambda token: '.*%s.*' % token, ERROR_TOKENS))
    error_re = re.compile(regex, re.IGNORECASE)

    lines_with_error_enum = filter(
        lambda tpl: error_re.match(tpl[1]),
        enumerate(content_lines, start=1))

    print_lines(lines_with_error_enum)
    _save_full_log(host, log_file, content)


def _print_wrapper(s):
    """Just a wrapper to make mocking easier on tests"""
    print(s.encode('utf-8'))
