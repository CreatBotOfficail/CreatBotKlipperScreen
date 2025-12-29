#!/usr/bin/python

import logging
import gi
from contextlib import suppress
from gi.repository import Gtk, Gdk, Pango, GLib, Gst, GObject, GdkPixbuf

Gst.init(None)
GObject.threads_init()

class VideoWidget(Gtk.DrawingArea):
    def __init__(self, width, height):
        super().__init__()
        self.set_size_request(width, height)
        self.connect("draw", self.on_draw)
        self.pixbuf = None
        self.width = width
        self.height = height
        self.last_frame_time = 0
        self.frame_counter = 0

    def on_draw(self, widget, cr):
        if self.pixbuf:
            try:
                Gdk.cairo_set_source_pixbuf(cr, self.pixbuf, 0, 0)
                cr.paint()

                allocation = widget.get_allocation()
                center_x = allocation.width / 2
                center_y = allocation.height / 2

                cr.set_source_rgb(1, 0, 0)
                cr.set_line_width(2)
                cr.move_to(0, center_y)
                cr.line_to(allocation.width, center_y)
                cr.move_to(center_x, 0)
                cr.line_to(center_x, allocation.height)
                cr.stroke()
            except Exception as e:
                logging.debug(f"failed: {e}")
        return False

    def set_pixbuf(self, pixbuf):
        self.pixbuf = pixbuf
        self.queue_draw()


class CameraController:
    def __init__(self, screen):
        self.screen = screen
        self.pipeline = None
        self.video_widget = None
        self.cam_config = {
            "stream_url": "/webrtc/stream.html?src=Alignment_RAW&mode=mjpeg",
            "service": "webrtc-go2rtc"
        }
        self.cam_loading_triggered = False
        self.load_timeout_id = None
        self.init_cam_label = None
        self.cam_box = None
        self.camera_container = None
        self.appsink = None
        self.pixsink = None
        self.is_playing = False
        self.connection_check_id = None
    
    def create_camera_display_area(self):
        main_container = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=0,
            halign=Gtk.Align.START,
            valign=Gtk.Align.CENTER,
        )

        camera_container = Gtk.EventBox()
        camera_container.set_size_request(*self._scaled(0.4, 0.5))
        camera_container.override_background_color(
            Gtk.StateFlags.NORMAL,
            Gdk.RGBA(0, 0, 0, 1)
        )
        camera_container.set_halign(Gtk.Align.CENTER)
        camera_container.set_valign(Gtk.Align.CENTER)
        camera_container.set_hexpand(True)
        camera_container.set_vexpand(True)

        self.init_cam_label = Gtk.Label()
        self.init_cam_label.set_text(_("Loading calibration camera..."))
        self.init_cam_label.set_halign(Gtk.Align.CENTER)
        self.init_cam_label.set_valign(Gtk.Align.CENTER)
        self.init_cam_label.set_line_wrap(True)
        self.init_cam_label.override_color(
            Gtk.StateFlags.NORMAL,
            Gdk.RGBA(1, 1, 1, 1)
        )
        camera_container.add(self.init_cam_label)
        main_container.add(camera_container)
        placeholder = Gtk.Box()
        main_container.pack_end(placeholder, True, True, 0)
        self.camera_container = camera_container
        self.cam_box = main_container
        main_container.show_all()
        
        return main_container

    def load_camera(self, widget=None):
        if widget is None:
            widget = self.camera_container
            if widget is None:
                logging.error("Camera container not initialized")
                return   
        if widget.get_parent():
            widget.get_parent().show_all()
        GLib.timeout_add(100, self._delayed_load_camera_real)
    
    def _delayed_load_camera_real(self):
        try:
            for child in self.camera_container.get_children():
                self.camera_container.remove(child)
            url = self._get_camera_url()
            self._stop_pipeline()
            width, height = self._get_container_size()
            self.video_widget = VideoWidget(width, height)
            self.camera_container.add(self.video_widget)
            self.video_widget.show()
            self._create_gstreamer_pipeline(url)
            self.pipeline.set_state(Gst.State.PLAYING)
            self.is_playing = True
            if self.init_cam_label:
                self.init_cam_label.set_text(_("Camera connected"))
            self._start_connection_check()
            if self.load_timeout_id:
                GLib.source_remove(self.load_timeout_id)
                self.load_timeout_id = None
            logging.info(f"Loading camera from {url}, Camera pipeline started successfully")
            
        except Exception as e:
            error_msg = str(e)[:80]
            logging.error(f"Load failed: {error_msg}", exc_info=True)
            if self.init_cam_label:
                self.init_cam_label.set_markup(f"<span color='red'>Error: {error_msg}</span>")
        
        return False
    
    def _create_gstreamer_pipeline(self, url):
        if url.startswith('rtsp://'):
            width = self.video_widget.width
            height = self.video_widget.height
            pipeline_desc = (
                f"rtspsrc location={url} latency=0 ! "
                "decodebin ! "  
                "videoconvert ! video/x-raw,format=RGB ! "
                f"videoscale ! video/x-raw,width={width},height={height} ! "
                "tee name=t ! "
                "queue ! "
                "appsink name=sink emit-signals=true max-buffers=2 drop=true "
                "t. ! "
                "queue ! "
                "gdkpixbufsink name=vsink"
            )
        else:
            logging.error(f"Unsupported URL scheme: {url}")
            return
        self.pipeline = Gst.parse_launch(pipeline_desc)
        self.appsink = self.pipeline.get_by_name("sink")
        self.appsink.connect("new-sample", self._on_new_sample)
        
        self.pixsink = self.pipeline.get_by_name("vsink")
        self.pixsink.connect("notify::last-pixbuf", self._on_new_pixbuf)
        
        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message::error", self._on_error)
        bus.connect("message::warning", self._on_warning)
        bus.connect("message::eos", self._on_eos)
    
    def _on_new_sample(self, sink):
        sample = sink.emit("pull-sample")
        if sample is None:
            return Gst.FlowReturn.ERROR
        
        buf = sample.get_buffer()
        caps = sample.get_caps()
        
        if not caps:
            return Gst.FlowReturn.ERROR
        structure = caps.get_structure(0)
        width = structure.get_value('width')
        height = structure.get_value('height')
        
        if width is None or height is None:
            return Gst.FlowReturn.ERROR
        result, mapinfo = buf.map(Gst.MapFlags.READ)
        if not result:
            return Gst.FlowReturn.ERROR
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_data(
                mapinfo.data,
                GdkPixbuf.Colorspace.RGB,
                False,
                8,
                width,
                height,
                width*3
            )
            if self.video_widget:
                GLib.idle_add(self.video_widget.set_pixbuf, pixbuf)
        finally:
            buf.unmap(mapinfo)
        
        return Gst.FlowReturn.OK
    
    def _on_new_pixbuf(self, sink, pspec):
        pixbuf = sink.get_property(pspec.name)
        if pixbuf and self.video_widget:
            GLib.idle_add(self.video_widget.set_pixbuf, pixbuf)
    
    def _on_error(self, bus, msg):
        err, debug = msg.parse_error()
        logging.error(f"GStreamer error: {err.message} - {debug}")
        if self.init_cam_label:
            self.init_cam_label.set_markup(f"<span color='red'>Error: {err.message[:60]}...</span>")
        self._reconnect_camera()
    
    def _on_warning(self, bus, msg):
        warn, debug = msg.parse_warning()
        logging.warning(f"GStreamer warning: {warn.message} - {debug}")
    
    def _on_eos(self, bus, msg):
        self._reconnect_camera()
    
    def _reconnect_camera(self):
        if self.is_playing:
            self._stop_pipeline()
            GLib.timeout_add_seconds(2, self._delayed_load_camera_real)
    
    def _stop_pipeline(self):
        if self.pipeline:
            try:
                self.pipeline.set_state(Gst.State.NULL)
                self.pipeline = None
                self.appsink = None
                self.pixsink = None
                self.is_playing = False
            except Exception as e:
                logging.error(f"Error stopping pipeline: {e}")
        self._stop_connection_check()
    
    def _start_connection_check(self):
        if self.connection_check_id:
            GLib.source_remove(self.connection_check_id)
        
        def check_connection():
            if not self.is_playing:
                logging.warning("Camera connection lost, attempting to reconnect...")
                self._reconnect_camera()
                return False
            return True
        self.connection_check_id = GLib.timeout_add_seconds(5, check_connection)
    
    def _stop_connection_check(self):
        if self.connection_check_id:
            GLib.source_remove(self.connection_check_id)
            self.connection_check_id = None
    
    def _get_container_size(self):
        if not self.camera_container:
            return self._scaled(0.4, 0.5)
        
        allocation = self.camera_container.get_allocation()
        width, height = allocation.width, allocation.height
        if width <= 0 or height <= 0:
            width, height = self._scaled(0.4, 0.5)
        return width, height
            
    def _get_camera_url(self):
        url = self.cam_config['stream_url']
        if url.startswith('/'):
            endpoint = self.screen._screen.apiclient.endpoint.split(':')
            url = f"{endpoint[0]}:{endpoint[1]}{url}"
        if self.cam_config.get('service') == 'webrtc-go2rtc':
            camera_name = url.split('?src=')[-1].split('&')[0] if '?src=' in url else 'Alignment_RAW'
            host = url.split('/')[2].split(':')[0] if url.startswith(('http://', 'https://')) else url
            url = f"rtsp://{host}:8554/{camera_name}"
            logging.info(f"go2rtc converted to RTSP: {url}")
        elif '/webrtc' in url:
            self.screen._screen.show_popup_message('WebRTC not supported, trying Stream')
            url = url.replace('/webrtc', '/stream')
        return url

    def init_cam_tip(self):
        if self.init_cam_label:
            self.init_cam_label.set_text(_("Loading calibration camera..."))

    def check_load_timeout(self):
        if not self.is_playing:
            if self.init_cam_label:
                self.init_cam_label.set_markup(_("<span color='red'>Load timeout!</span>"))
            return False
        return True
    
    def delayed_load_camera(self):
        if self.camera_container and self.camera_container.get_window():
            self.cam_loading_triggered = True
            self.load_camera(self.camera_container)
        return False
    
    def deactivate(self):
        self._stop_pipeline()
        self.cam_loading_triggered = False
        if self.camera_container:
            children = list(self.camera_container.get_children())
            for child in children:
                self.camera_container.remove(child)
            if self.init_cam_label:
                self.camera_container.add(self.init_cam_label)
                self.init_cam_label.set_text(_("Loading calibration camera..."))
        self.video_widget = None
        if self.load_timeout_id:
            GLib.source_remove(self.load_timeout_id)
            self.load_timeout_id = None
    
    def _scaled(self, w_rate: float, h_rate=None):
        h_rate = h_rate or w_rate
        try:
            return (int(self.screen._gtk.content_width * w_rate),
                    int(self.screen._gtk.content_height * h_rate))
        except Exception:
            return (100, 100)
