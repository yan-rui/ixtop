# This file is part of nvhtop, the interactive Nvidia-GPU process viewer.
# License: GNU GPL version 3.

# pylint: disable=missing-module-docstring,missing-class-docstring,missing-function-docstring
# pylint: disable=invalid-name,line-too-long

import time
from collections import OrderedDict

import psutil
from cachetools.func import ttl_cache

from .displayable import Displayable
from .utils import (nvml_query, nvml_check_return,
                    colored, cut_string, bytes2human, timedelta2human)


class DevicePanel(Displayable):
    def __init__(self, devices, compact, win):
        super(DevicePanel, self).__init__(win)

        self.devices = devices
        self.device_count = len(self.devices)
        self._compact = compact
        self.width = 79
        self.height = 4 + (3 - int(compact)) * (self.device_count + 1)
        self.full_height = 4 + 3 * (self.device_count + 1)
        if self.device_count == 0:
            self.height = self.full_height = 6

        self.driver_version = str(nvml_query('nvmlSystemGetDriverVersion'))
        cuda_version = nvml_query('nvmlSystemGetCudaDriverVersion')
        if nvml_check_return(cuda_version, int):
            self.cuda_version = str(cuda_version // 1000 + (cuda_version % 1000) / 100)
        else:
            self.cuda_version = 'N/A'

        self.formats_compact = [
            '│ {index:>3} {fan_speed:>3} {temperature:>4} {performance_state:>3} {power_state:>12} '
            '│ {memory_usage:>20} │ {gpu_utilization:>7}  {compute_mode:>11} │'
        ]
        self.formats_full = [
            '│ {index:>3}  {name:>18}  {persistence_mode:<4} '
            '│ {bus_id:<16} {display_active:>3} │ {ecc_errors:>20} │',
            '│ {fan_speed:>3}  {temperature:>4}  {performance_state:>4}  {power_state:>12} '
            '│ {memory_usage:>20} │ {gpu_utilization:>7}  {compute_mode:>11} │'
        ]

        self.snapshots = []

    @property
    def compact(self):
        return self._compact

    @compact.setter
    def compact(self, value):
        if self._compact != value:
            self.need_redraw = True
            self._compact = value
            self.height = 4 + (3 - int(self.compact)) * (self.device_count + 1)

    def header_lines(self):
        header = [
            '╒═════════════════════════════════════════════════════════════════════════════╕',
            '│ NVIDIA-SMI {0:<6}       Driver Version: {0:<6}       CUDA Version: {1:<5}    │'.format(self.driver_version,
                                                                                                      self.cuda_version),
        ]
        if self.device_count > 0:
            header.append('├───────────────────────────────┬──────────────────────┬──────────────────────┤')
            if self.compact:
                header.append('│ GPU Fan Temp Perf Pwr:Usg/Cap │         Memory-Usage │ GPU-Util  Compute M. │')
            else:
                header.extend([
                    '│ GPU  Name        Persistence-M│ Bus-Id        Disp.A │ Volatile Uncorr. ECC │',
                    '│ Fan  Temp  Perf  Pwr:Usage/Cap│         Memory-Usage │ GPU-Util  Compute M. │'
                ])
            header.append('╞═══════════════════════════════╪══════════════════════╪══════════════════════╡')
        else:
            header.extend([
                '╞═════════════════════════════════════════════════════════════════════════════╡',
                '│  No visible CUDA device found                                               │',
                '╘═════════════════════════════════════════════════════════════════════════════╛'
            ])
        return header

    def frame_lines(self):
        frame = self.header_lines()
        if self.device_count > 0:
            if self.compact:
                frame.extend(self.device_count * [
                    '│                               │                      │                      │',
                    '├───────────────────────────────┼──────────────────────┼──────────────────────┤'
                ])
            else:
                frame.extend(self.device_count * [
                    '│                               │                      │                      │',
                    '│                               │                      │                      │',
                    '├───────────────────────────────┼──────────────────────┼──────────────────────┤'
                ])
            frame.pop()
            frame.append('╘═══════════════════════════════╧══════════════════════╧══════════════════════╛')
        return frame

    def take_snapshot(self):
        self.snapshots.clear()
        self.snapshots.extend(map(lambda device: device.snapshot(), self.devices))

    def poke(self):
        self.take_snapshot()

        super(DevicePanel, self).poke()

    def draw(self):
        self.color_reset()

        if self.need_redraw:
            self.addstr(self.y, self.x + 62, '(Press q to Quit)')
            self.color_at(self.y, self.x + 69, width=1, fg='magenta', attr='bold | italic')
            for y, line in enumerate(self.frame_lines(), start=self.y + 1):
                self.addstr(y, self.x, line)

        self.addstr(self.y, self.x, '{:<62}'.format(time.strftime('%a %b %d %H:%M:%S %Y')))

        if self.compact:
            formats = self.formats_compact
        else:
            formats = self.formats_full
        for index, device in enumerate(self.devices):
            device = device.snapshot()
            device.name = cut_string(device.name, maxlen=18)
            for y, fmt in enumerate(formats, start=self.y + 4 + (len(formats) + 1) * (index + 1)):
                self.addstr(y, self.x, fmt.format(**device.__dict__))
                self.color_at(y, 2, width=29, fg=device.display_color)
                self.color_at(y, 34, width=20, fg=device.display_color)
                self.color_at(y, 57, width=20, fg=device.display_color)

    def finalize(self):
        self.need_redraw = False

    def print(self):
        self.take_snapshot()

        lines = [
            '{:<79}'.format(time.strftime('%a %b %d %H:%M:%S %Y')),
            *self.header_lines()
        ]

        if self.device_count > 0:
            for device in self.devices:
                device = device.snapshot()
                device.name = cut_string(device.name, maxlen=18)

                def colorize(s):
                    return colored(s, device.display_color)  # pylint: disable=cell-var-from-loop

                for fmt in self.formats_full:
                    line = fmt.format(**device.__dict__)
                    lines.append('│'.join(map(colorize, line.split('│'))))

                lines.append('├───────────────────────────────┼──────────────────────┼──────────────────────┤')
            lines.pop()
            lines.append('╘═══════════════════════════════╧══════════════════════╧══════════════════════╛')

        print('\n'.join(lines))


class ProcessPanel(Displayable):
    def __init__(self, devices, win=None):
        super(ProcessPanel, self).__init__(win)
        self.width = 79
        self.height = 6

        self.devices = devices

        self.snapshots = []

    def header_lines(self):
        header = [
            '╒═════════════════════════════════════════════════════════════════════════════╕',
            '│ Processes:                                                                  │',
            '│ GPU    PID    USER  GPU MEM  %CPU  %MEM      TIME  COMMAND                  │',
            '╞═════════════════════════════════════════════════════════════════════════════╡'
        ]
        if len(self.snapshots) == 0:
            header.extend([
                '│  No running compute processes found                                         │',
                '╘═════════════════════════════════════════════════════════════════════════════╛'
            ])
        return header

    def take_snapshot(self):
        self.snapshots.clear()
        self.snapshots.extend(map(lambda process: process.snapshot(), self.processes.values()))

    def poke(self):
        self.take_snapshot()
        n_processes = len(self.snapshots)
        n_used_devices = len(set([p.device.index for p in self.snapshots]))
        if n_processes > 0:
            height = 5 + n_processes + n_used_devices - 1
        else:
            height = 6
        self.need_redraw = (self.need_redraw or self.height > height)
        self.height = height

        super(ProcessPanel, self).poke()

    @property
    @ttl_cache(ttl=1.0)
    def processes(self):
        processes = {}
        for device in self.devices:
            for p in device.processes.values():
                try:
                    processes[(p.device.index, p.username(), p.pid)] = p
                except psutil.Error:
                    pass
        return OrderedDict([(key[-1], processes[key]) for key in sorted(processes.keys())])

    def draw(self):
        self.color_reset()

        if self.need_redraw:
            for y, line in enumerate(self.header_lines(), start=self.y):
                self.addstr(y, self.x, line)

        if len(self.snapshots) > 0:
            y = self.y + 4
            prev_device_index = None
            color = -1
            for process in self.snapshots:
                device_index = process.device.index
                if prev_device_index is None or prev_device_index != device_index:
                    color = process.device.display_color
                try:
                    cmdline = process.cmdline
                    cmdline[0] = process.name
                except IndexError:
                    cmdline = ['Terminated']
                cmdline = cut_string(' '.join(cmdline).strip(), maxlen=24)

                if prev_device_index is not None and prev_device_index != device_index:
                    self.addstr(y, self.x,
                                '├─────────────────────────────────────────────────────────────────────────────┤')
                    y += 1
                prev_device_index = device_index
                self.addstr(y, self.x,
                            '│ {:>3} {:>6} {:>7} {:>8} {:>5.1f} {:>5.1f}  {:>8}  {:<24} │'.format(
                                device_index, process.pid, cut_string(process.username, maxlen=7, padstr='+'),
                                bytes2human(process.gpu_memory), process.cpu_percent,
                                process.memory_percent, timedelta2human(process.running_time),
                                cmdline
                            ))
                self.color_at(y, self.x + 2, width=3, fg=color)
                y += 1
            self.addstr(y, self.x, '╘═════════════════════════════════════════════════════════════════════════════╛')

    def finalize(self):
        self.need_redraw = False

    def print(self):
        self.take_snapshot()

        lines = self.header_lines()

        if len(self.snapshots) > 0:
            prev_device_index = None
            color = None
            for process in self.snapshots:
                device_index = process.device.index
                if prev_device_index is None or prev_device_index != device_index:
                    color = process.device.display_color
                try:
                    cmdline = process.cmdline
                    cmdline[0] = process.name
                except IndexError:
                    cmdline = ['Terminated']
                cmdline = cut_string(' '.join(cmdline).strip(), maxlen=24)

                if prev_device_index is not None and prev_device_index != device_index:
                    lines.append('├─────────────────────────────────────────────────────────────────────────────┤')
                prev_device_index = device_index
                lines.append('│ {} {:>6} {:>7} {:>8} {:>5.1f} {:>5.1f}  {:>8}  {:<24} │'.format(
                    colored('{:>3}'.format(device_index), color), process.pid,
                    cut_string(process.username, maxlen=7, padstr='+'),
                    bytes2human(process.gpu_memory), process.cpu_percent, process.memory_percent,
                    timedelta2human(process.running_time), cmdline
                ))

            lines.append('╘═════════════════════════════════════════════════════════════════════════════╛')

        print('\n'.join(lines))