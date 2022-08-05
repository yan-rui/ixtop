# This file is part of nvitop, the interactive NVIDIA-GPU process viewer.
# License: GNU GPL version 3.

# pylint: disable=missing-module-docstring,missing-class-docstring,missing-function-docstring

import threading
import time

from nvitop.gui.library import (
    NA,
    BufferedHistoryGraph,
    Device,
    Displayable,
    colored,
    host,
    make_bar,
)


class HostPanel(Displayable):  # pylint: disable=too-many-instance-attributes
    NAME = 'host'

    SNAPSHOT_INTERVAL = 0.5

    def __init__(self, devices, compact, win, root):
        super().__init__(win, root)

        self.devices = devices
        self.device_count = len(self.devices)

        if win is not None:
            self.average_memory_percent = None
            self.average_gpu_utilization = None
            self.enable_history()

        self._compact = compact
        self.width = max(79, root.width)
        self.full_height = 12
        self.compact_height = 2
        self.height = self.compact_height if compact else self.full_height

        self.cpu_percent = None
        self.load_average = None
        self.memory_percent = None
        self.swap_percent = None
        self._snapshot_daemon = threading.Thread(
            name='host-snapshot-daemon', target=self._snapshot_target, daemon=True
        )
        self._daemon_running = threading.Event()

    @property
    def width(self):
        return self._width

    @width.setter
    def width(self, value):
        width = max(79, value)
        if self._width != width:
            if self.visible:
                self.need_redraw = True
            graph_width = max(width - 80, 20)
            if self.win is not None:
                self.average_memory_percent.width = graph_width
                self.average_gpu_utilization.width = graph_width
                for device in self.devices:
                    device.memory_percent.history.width = graph_width
                    device.gpu_utilization.history.width = graph_width
        self._width = width

    @property
    def compact(self):
        return self._compact or self.ascii

    @compact.setter
    def compact(self, value):
        value = value or self.ascii
        if self._compact != value:
            self.need_redraw = True
            self._compact = value
            self.height = self.compact_height if self.compact else self.full_height

    def enable_history(self):
        host.cpu_percent = BufferedHistoryGraph(
            interval=1.0,
            width=77,
            height=5,
            upsidedown=False,
            baseline=0.0,
            upperbound=100.0,
            dynamic_bound=False,
            format='CPU: {:.1f}%'.format,
        )(host.cpu_percent)
        host.memory_percent = BufferedHistoryGraph(
            interval=1.0,
            width=77,
            height=4,
            upsidedown=True,
            baseline=0.0,
            upperbound=100.0,
            dynamic_bound=False,
            format='MEM: {:.1f}%'.format,
        )(host.memory_percent)
        host.swap_percent = BufferedHistoryGraph(
            interval=1.0,
            width=77,
            height=1,
            upsidedown=False,
            baseline=0.0,
            upperbound=100.0,
            dynamic_bound=False,
            format='SWP: {:.1f}%'.format,
        )(host.swap_percent)

        def percentage(x):
            if x is NA:
                return NA
            return '{:.1f}%'.format(x)

        def enable_history(device):
            device.memory_percent = BufferedHistoryGraph(
                interval=1.0,
                width=20,
                height=5,
                upsidedown=False,
                baseline=0.0,
                upperbound=100.0,
                dynamic_bound=False,
                format=lambda x: ('GPU {} MEM: {}').format(device.display_index, percentage(x)),
            )(device.memory_percent)
            device.gpu_utilization = BufferedHistoryGraph(
                interval=1.0,
                width=20,
                height=5,
                upsidedown=True,
                baseline=0.0,
                upperbound=100.0,
                dynamic_bound=False,
                format=lambda x: ('GPU {} UTL: {}').format(device.display_index, percentage(x)),
            )(device.gpu_utilization)

        for device in self.devices:
            enable_history(device)

        prefix = 'AVG ' if self.device_count > 1 else ''
        self.average_memory_percent = BufferedHistoryGraph(
            interval=1.0,
            width=20,
            height=5,
            upsidedown=False,
            baseline=0.0,
            upperbound=100.0,
            dynamic_bound=False,
            format=lambda x: ('{}GPU MEM: {}').format(prefix, percentage(x)),
        )
        self.average_gpu_utilization = BufferedHistoryGraph(
            interval=1.0,
            width=32,
            height=5,
            upsidedown=True,
            baseline=0.0,
            upperbound=100.0,
            dynamic_bound=False,
            format=lambda x: ('{}GPU UTL: {}').format(prefix, percentage(x)),
        )

    def take_snapshots(self):
        host.cpu_percent()
        host.memory_percent()
        host.swap_percent()
        self.load_average = host.load_average()

        self.cpu_percent = host.cpu_percent.history.last_value
        self.memory_percent = host.memory_percent.history.last_value
        self.swap_percent = host.swap_percent.history.last_value

        total_memory_used = 0
        total_memory_total = 0
        gpu_utilizations = []
        for device in self.devices:
            memory_used = device.snapshot.memory_used
            memory_total = device.snapshot.memory_total
            gpu_utilization = device.snapshot.gpu_utilization
            if memory_used is not NA and memory_total is not NA:
                total_memory_used += memory_used
                total_memory_total += memory_total
            if gpu_utilization is not NA:
                gpu_utilizations.append(float(gpu_utilization))
        if total_memory_total > 0:
            self.average_memory_percent.add(100.0 * total_memory_used / total_memory_total)
        if len(gpu_utilizations) > 0:
            self.average_gpu_utilization.add(sum(gpu_utilizations) / len(gpu_utilizations))

    def _snapshot_target(self):
        self._daemon_running.wait()
        while self._daemon_running.is_set():
            self.take_snapshots()
            time.sleep(self.SNAPSHOT_INTERVAL)

    def frame_lines(self, compact=None):
        if compact is None:
            compact = self.compact
        if compact or self.ascii:
            return []

        remaining_width = self.width - 79
        data_line = (
            '│                                                                             │'
        )
        separator_line = (
            '├────────────╴120s├─────────────────────────╴60s├──────────╴30s├──────────────┤'
        )
        if self.width >= 100:
            data_line += ' ' * (remaining_width - 1) + '│'
            separator_line = separator_line[:-1] + '┼' + '─' * (remaining_width - 1) + '┤'

        frame = [
            '╞═══════════════════════════════╧══════════════════════╧══════════════════════╡',
            data_line,
            data_line,
            data_line,
            data_line,
            data_line,
            separator_line,
            data_line,
            data_line,
            data_line,
            data_line,
            data_line,
            '╘═════════════════════════════════════════════════════════════════════════════╛',
        ]
        if self.width >= 100:
            frame[0] = frame[0][:-1] + '╪' + '═' * (remaining_width - 1) + '╡'
            frame[-1] = frame[-1][:-1] + '╧' + '═' * (remaining_width - 1) + '╛'

        return frame

    def poke(self):
        if not self._daemon_running.is_set():
            self._daemon_running.set()
            self._snapshot_daemon.start()
            self.take_snapshots()

        super().poke()

    def draw(self):  # pylint: disable=too-many-locals,too-many-branches,too-many-statements
        self.color_reset()

        if self.load_average is not None:
            load_average = tuple(
                '{:5.2f}'.format(value)[:5] if value < 10000.0 else '9999+'
                for value in self.load_average
            )
        else:
            load_average = (NA,) * 3
        load_average = 'Load Average: {} {} {}'.format(*load_average)

        if self.compact:
            width_right = len(load_average) + 4
            width_left = self.width - 2 - width_right
            cpu_bar = '[ {} ]'.format(make_bar('CPU', self.cpu_percent, width_left - 4))
            memory_bar = '[ {} ]'.format(make_bar('MEM', self.memory_percent, width_left - 4))
            swap_bar = '[ {} ]'.format(make_bar('SWP', self.swap_percent, width_right - 4))
            self.addstr(self.y, self.x, '{}  ( {} )'.format(cpu_bar, load_average))
            self.addstr(self.y + 1, self.x, '{}  {}'.format(memory_bar, swap_bar))
            self.color_at(self.y, self.x, width=len(cpu_bar), fg='cyan', attr='bold')
            self.color_at(self.y + 1, self.x, width=width_left, fg='magenta', attr='bold')
            self.color_at(self.y, self.x + width_left + 2, width=width_right, attr='bold')
            self.color_at(
                self.y + 1, self.x + width_left + 2, width=width_right, fg='blue', attr='bold'
            )
            return

        remaining_width = self.width - 79

        if self.need_redraw:
            for y, line in enumerate(self.frame_lines(), start=self.y - 1):
                self.addstr(y, self.x, line)
            self.color_at(self.y + 5, self.x + 14, width=4, attr='dim')
            self.color_at(self.y + 5, self.x + 45, width=3, attr='dim')
            self.color_at(self.y + 5, self.x + 60, width=3, attr='dim')

            if self.width >= 100:
                for offset, string in (
                    (20, '╴30s├'),
                    (35, '╴60s├'),
                    (66, '╴120s├'),
                    (126, '╴240s├'),
                ):
                    if offset > remaining_width:
                        break
                    self.addstr(self.y + 5, self.x + self.width - offset, string)
                    self.color_at(
                        self.y + 5,
                        self.x + self.width - offset + 1,
                        width=len(string) - 2,
                        attr='dim',
                    )

        self.color(fg='cyan')
        for y, line in enumerate(host.cpu_percent.history.graph, start=self.y):
            self.addstr(y, self.x + 1, line)

        self.color(fg='magenta')
        for y, line in enumerate(host.memory_percent.history.graph, start=self.y + 6):
            self.addstr(y, self.x + 1, line)

        self.color(fg='blue')
        for y, line in enumerate(host.swap_percent.history.graph, start=self.y + 10):
            self.addstr(y, self.x + 1, line)

        if self.width >= 100:
            if self.device_count > 1 and self.parent.selected.is_set():
                device = self.parent.selected.process.device
                memory_percent = device.memory_percent.history
                gpu_utilization = device.gpu_utilization.history
            else:
                memory_percent = self.average_memory_percent
                gpu_utilization = self.average_gpu_utilization

            if self.TERM_256COLOR:
                for i, (y, line) in enumerate(enumerate(memory_percent.graph, start=self.y)):
                    self.addstr(y, self.x + 79, line, self.get_fg_bg_attr(fg=1.0 - i / 4.0))

                for i, (y, line) in enumerate(enumerate(gpu_utilization.graph, start=self.y + 6)):
                    self.addstr(y, self.x + 79, line, self.get_fg_bg_attr(fg=i / 4.0))
            else:
                self.color(fg=Device.color_of(memory_percent.last_value, type='memory'))
                for y, line in enumerate(memory_percent.graph, start=self.y):
                    self.addstr(y, self.x + 79, line)

                self.color(fg=Device.color_of(gpu_utilization.last_value, type='gpu'))
                for y, line in enumerate(gpu_utilization.graph, start=self.y + 6):
                    self.addstr(y, self.x + 79, line)

            self.color_reset()
            self.addstr(self.y, self.x + 1, ' {} '.format(load_average))
            self.addstr(self.y + 1, self.x + 1, ' {} '.format(host.cpu_percent.history))
            self.addstr(
                self.y + 9,
                self.x + 1,
                ' {} '.format(host.memory_percent.history),
            )
            self.addstr(
                self.y + 10,
                self.x + 1,
                ' {} '.format(host.swap_percent.history),
            )
            self.addstr(self.y, self.x + 79, ' {} '.format(memory_percent))
            self.addstr(self.y + 10, self.x + 79, ' {} '.format(gpu_utilization))

    def destroy(self):
        super().destroy()
        self._daemon_running.clear()

    def print_width(self):
        if self.device_count > 0 and self.width >= 100:
            return self.width
        return 79

    def print(self):
        self.cpu_percent = host.cpu_percent()
        self.memory_percent = host.memory_percent()
        self.swap_percent = host.swap_percent()
        self.load_average = host.load_average()

        if self.load_average is not None:
            load_average = tuple(
                '{:5.2f}'.format(value)[:5] if value < 10000.0 else '9999+'
                for value in self.load_average
            )
        else:
            load_average = (NA,) * 3
        load_average = 'Load Average: {} {} {}'.format(*load_average)

        width_right = len(load_average) + 4
        width_left = self.width - 2 - width_right
        cpu_bar = '[ {} ]'.format(make_bar('CPU', self.cpu_percent, width_left - 4))
        memory_bar = '[ {} ]'.format(make_bar('MEM', self.memory_percent, width_left - 4))
        swap_bar = '[ {} ]'.format(make_bar('SWP', self.swap_percent, width_right - 4))

        lines = [
            '{}  {}'.format(
                colored(cpu_bar, color='cyan', attrs=('bold',)),
                colored('( {} )'.format(load_average), attrs=('bold',)),
            ),
            '{}  {}'.format(
                colored(memory_bar, color='magenta', attrs=('bold',)),
                colored(swap_bar, color='blue', attrs=('bold',)),
            ),
        ]

        lines = '\n'.join(lines)
        if self.ascii:
            lines = lines.translate(self.ASCII_TRANSTABLE)

        try:
            print(lines)
        except UnicodeError:
            print(lines.translate(self.ASCII_TRANSTABLE))

    def press(self, key):
        self.root.keymaps.use_keymap('host')
        self.root.press(key)
