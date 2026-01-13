
import logging
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
from contextlib import suppress
from ks_includes.screen_panel import ScreenPanel


class Panel(ScreenPanel):
    def __init__(self, screen, title):
        title = title or _("Camera")
        super().__init__(screen, title)
        self.mpv = None
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        for i, cam in enumerate(self._printer.cameras):
            if not cam["enabled"]:
                continue
            logging.info(cam)
            cam[cam["name"]] = self._gtk.Button(
                image_name="camera", label=cam["name"], style=f"color{i % 4 + 1}",
                scale=self.bts, position=Gtk.PositionType.LEFT, lines=1
            )
            cam[cam["name"]].set_hexpand(True)
            cam[cam["name"]].set_vexpand(True)
            cam[cam["name"]].connect("clicked", self.play, cam)
            box.add(cam[cam["name"]])

        self.scroll = self._gtk.ScrolledWindow()
        self.scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.scroll.add(box)
        self.content.add(self.scroll)
        self.content.show_all()

    def activate(self):
        # if only 1 cam start playing fullscreen
        if len(self._printer.cameras) == 1:
            cam = next(iter(self._printer.cameras))
            if cam['enabled']:
                self.play(None, cam)

    def deactivate(self):
        if self.mpv:
            self.mpv.terminate()
            self.mpv = None

    def play(self, widget, cam):
        url = cam['stream_url']
        if url.startswith('/'):
            logging.info("camera URL is relative")
            endpoint = self._screen.apiclient.endpoint.split(':')
            url = f"{endpoint[0]}:{endpoint[1]}{url}"
        # Check if service is go2rtc and modify URL for RTSP streaming
        if cam.get('service') == 'webrtc-go2rtc':
            camera_name = 'Camera'
            if '?src=' in url:
                camera_name = url.split('?src=')[-1].split('&')[0]

            if url.startswith('http://') or url.startswith('https://'):
                url_parts = url.split('/')
                host_port = url_parts[2]
                if ':' in host_port:
                    host = host_port.split(':')[0]
                else:
                    host = host_port

                url = f"rtsp://{host}:8554/{camera_name}"

            logging.info(f"go2rtc service detected, converted to RTSP stream: {url}")
        elif '/webrtc' in url:
            self._screen.show_popup_message(_('WebRTC is not supported by the backend trying Stream'))
            url = url.replace('/webrtc', '/stream')
        vf = ""
        if cam["flip_horizontal"]:
            vf += "hflip,"
        if cam["flip_vertical"]:
            vf += "vflip,"
        vf += f"rotate:{cam['rotation'] * 3.14159 / 180}"
        logging.info(f"video filters: {vf}")

        if self.mpv:
            self.mpv.terminate()

        try:
            gi.require_version('Gst', '1.0')
            gi.require_version('GstVideo', '1.0')
        except ValueError:
            pass
        from gi.repository import Gst, Gdk, GLib, Pango

        if not Gst.is_initialized():
            Gst.init(None)

        class VideoWidget(Gtk.DrawingArea):
            def __init__(self):
                super().__init__()
                self.connect("draw", self.on_draw)
                self.pixbuf = None

            def on_draw(self, widget, cr):
                if self.pixbuf:
                    try:
                        Gdk.cairo_set_source_pixbuf(cr, self.pixbuf, 0, 0)
                        cr.paint()
                    except Exception:
                        pass
                return False

            def set_pixbuf(self, pixbuf):
                self.pixbuf = pixbuf
                self.queue_draw()

        class GstPlayer:
            def __init__(self_inner):
                self_inner.pipeline = None
                self_inner.window = None
                self_inner.loop = None
                self_inner.video_widget = None

            def terminate(self_inner):
                if self_inner.pipeline:
                    self_inner.pipeline.set_state(Gst.State.NULL)
                if self_inner.window:
                    with suppress(Exception):
                        self_inner.window.destroy()
                if self_inner.loop and self_inner.loop.is_running():
                    self_inner.loop.quit()

        self.mpv = GstPlayer()
        self.mpv.video_widget = VideoWidget()
        
        screen = Gdk.Screen.get_default()
        width = screen.get_width() if screen else 1024
        height = screen.get_height() if screen else 600
        
        pipeline_parts = []
        if url.startswith("rtsp"):
            # Hardware accelerated pipeline for RTSP as requested
            pipeline_parts.append(f"rtspsrc location={url} latency=0")
            pipeline_parts.append("rtph264depay")
            pipeline_parts.append("h264parse")
            pipeline_parts.append("mppvideodec")
            pipeline_parts.append("videoconvert")
            pipeline_parts.append("video/x-raw,format=RGB")
        else:
            # Generic fallback
            pipeline_parts.append(f"urisourcebin uri={url}")
            pipeline_parts.append("decodebin")
            pipeline_parts.append("videoconvert")

        if cam["flip_horizontal"]:
            pipeline_parts.append("videoflip method=horizontal-flip")
        if cam["flip_vertical"]:
            pipeline_parts.append("videoflip method=vertical-flip")

        rot = cam.get('rotation', 0)
        if rot == 90:
            pipeline_parts.append("videoflip method=clockwise")
        elif rot == 180:
            pipeline_parts.append("videoflip method=rotate-180")
        elif rot == 270:
            pipeline_parts.append("videoflip method=counterclockwise")

        # Force format and scale
        pipeline_parts.append(f"videoscale ! video/x-raw,width={width},height={height}")
        pipeline_parts.append("gdkpixbufsink name=sink")

        try:
            launch_str = " ! ".join(pipeline_parts)
            logging.info(f"Gst launch: {launch_str}")
            self.mpv.pipeline = Gst.parse_launch(launch_str)
        except Exception as e:
            logging.exception("Failed to launch gst")
            self._screen.show_popup_message(f"Gst Error: {e}")
            self.mpv = None
            return

        self.mpv.window = Gtk.Window()
        self.mpv.window.fullscreen()
        
        # UX Improvement: Black background + Spinner
        self.mpv.window.override_background_color(Gtk.StateFlags.NORMAL, Gdk.RGBA(0, 0, 0, 1))
        
        overlay = Gtk.Overlay()
        overlay.add(self.mpv.video_widget)
        
        spinner = Gtk.Label()
        spinner.set_markup(f"<span color='white' font_size='large'>{_('Loading...')}</span>")
        spinner.set_halign(Gtk.Align.CENTER)
        spinner.set_valign(Gtk.Align.CENTER)
        
        overlay.add_overlay(spinner)
        
        self.mpv.window.add(overlay)

        def on_new_pixbuf(sink, pspec):
            pixbuf = sink.get_property(pspec.name)
            if pixbuf and self.mpv and self.mpv.video_widget:
                GLib.idle_add(self.mpv.video_widget.set_pixbuf, pixbuf)
                GLib.idle_add(spinner.hide) 

        sink = self.mpv.pipeline.get_by_name("sink")
        sink.connect("notify::last-pixbuf", on_new_pixbuf)

        def quit_player(*args):
             self.mpv.terminate()

        self.mpv.window.connect("button-press-event", quit_player)
        self.mpv.window.connect("destroy", quit_player)

        bus = self.mpv.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message::eos", quit_player)
        bus.connect("message::error", quit_player)

        self.mpv.window.show_all()
        self.mpv.pipeline.set_state(Gst.State.PLAYING)

        self.mpv.loop = GLib.MainLoop()
        try:
            self.mpv.loop.run()
        except:
            pass

        self.mpv.terminate()
        self.mpv = None
        if len(self._printer.cameras) == 1:
            self._screen._menu_go_back()

    def log(self, loglevel, component, message):
        logging.debug(f'[{loglevel}] {component}: {message}')
        if loglevel == 'error' and 'No Xvideo support found' not in message and 'youtube-dl' not in message:
            self._screen.show_popup_message(f'{message}')
