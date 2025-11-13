from gi.repository import Gtk
import gi

gi.require_version("Gtk", "3.0")


class TimerKeypad(Gtk.Box):
    def __init__(self, screen, change_timer, close_function):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)

        self.labels = {}
        self.change_timer = change_timer
        self.close_function = close_function
        self.screen = screen
        self._gtk = screen.gtk

        numpad = Gtk.Grid(row_homogeneous=True, column_homogeneous=True)
        numpad.set_direction(Gtk.TextDirection.LTR)
        numpad.get_style_context().add_class('numpad')

        keys = [
            ['1', 'numpad_tleft'],
            ['2', 'numpad_top'],
            ['3', 'numpad_tright'],
            ['4', 'numpad_left'],
            ['5', 'numpad_button'],
            ['6', 'numpad_right'],
            ['7', 'numpad_left'],
            ['8', 'numpad_button'],
            ['9', 'numpad_right'],
            ['.', 'numpad_bleft'],
            ['0', 'numpad_bottom'],
            ['B', 'numpad_bright']
        ]
        for i in range(len(keys)):
            k_id = f'button_{str(keys[i][0])}'
            if keys[i][0] == "B":
                self.labels[k_id] = self._gtk.Button("backspace", scale=1)
            else:
                self.labels[k_id] = Gtk.Button(label=keys[i][0])
            self.labels[k_id].connect('clicked', self.update_entry, keys[i][0])
            self.labels[k_id].get_style_context().add_class(keys[i][1])
            self.labels[k_id].get_style_context().add_class("numpad_key")
            numpad.attach(self.labels[k_id], i % 3, i // 3, 1, 1)

        self.labels['entry'] = Gtk.Entry()
        self.labels['entry'].set_size_request(-1, 65)
        self.labels['entry'].props.xalign = 0.5
        self.labels['entry'].connect("activate", self.update_entry, "E")

        bottom_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, homogeneous=True, spacing=10)

        cancel_btn = self._gtk.Button("cancel", scale=0.6)
        cancel_btn.connect("clicked", self.close_function)

        always_on_btn = self._gtk.Button(
            None, _("Always On"), None, .66, Gtk.PositionType.RIGHT, 1)
        always_on_btn.connect("clicked", self.set_always_on)

        confirm_btn = self._gtk.Button("enter", scale=1.4)
        confirm_btn.connect("clicked", self.update_entry, "E")

        bottom_box.pack_start(cancel_btn, True, True, 0)
        bottom_box.pack_start(always_on_btn, True, True, 0)
        bottom_box.pack_start(confirm_btn, True, True, 0)

        self.add(self.labels['entry'])
        self.add(numpad)
        self.add(bottom_box)

    def clear(self):
        self.labels['entry'].set_text("")

    def clear_and_close(self):
        self.clear()
        self.close_function()

    def set_always_on(self, widget):
        self.change_timer(0)
        self.clear_and_close()

    def update_entry(self, widget, digit):
        text = self.labels['entry'].get_text()
        if digit == 'B':
            if len(text) < 1:
                return
            self.labels['entry'].set_text(text[:-1])
        elif digit == 'E':
            hours = self.validate_hours(text)
            self.change_timer(hours)
            self.clear_and_close()
        elif digit == '.':
            if '.' not in text and len(text) > 0:
                self.labels['entry'].set_text(text + digit)
        elif digit.isdigit():
            if len(text) < 5:
                self.labels['entry'].set_text(text + digit)

    @staticmethod
    def validate_hours(hours_str):
        try:
            hours = float(hours_str)
            return max(0, hours)
        except ValueError:
            return 0
