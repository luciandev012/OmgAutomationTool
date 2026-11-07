"""Scrollable tool controls, including mouse-wheel support scoped to this frame."""
import tkinter as tk
from tkinter import ttk


class ScrollableFrame(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(self, highlightthickness=0, width=1, height=1)
        self.vertical = ttk.Scrollbar(self, orient='vertical', command=self.canvas.yview)
        self.horizontal = ttk.Scrollbar(self, orient='horizontal', command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=self.vertical.set, xscrollcommand=self.horizontal.set)
        self.canvas.grid(row=0, column=0, sticky='nsew')
        self.vertical.grid(row=0, column=1, sticky='ns')
        self.horizontal.grid(row=1, column=0, sticky='ew')
        self.content = ttk.Frame(self.canvas)
        self.item = self.canvas.create_window(0, 0, window=self.content, anchor='nw')
        self.content.bind('<Configure>', self._sync_region)
        self.canvas.bind('<Configure>', self._resize_content)
        self._wheel_tag = f'ToolScroll:{self}'
        self.bind_class(self._wheel_tag, '<MouseWheel>', self._mousewheel)
        self.bind('<Destroy>', self._cleanup, add='+')

    def _sync_region(self, _event=None):
        width=max(self.canvas.winfo_width(), self.content.winfo_reqwidth())
        self.canvas.itemconfigure(self.item, width=width)
        self.canvas.configure(scrollregion=self.canvas.bbox('all'))

    def _resize_content(self, event):
        self.canvas.itemconfigure(self.item, width=max(event.width, self.content.winfo_reqwidth()))
        self._sync_region()

    def enable_mousewheel(self):
        # A private bindtag precedes control bindings so wheel scrolling over a
        # combobox/spinbox scrolls the page, rather than changing its value.
        def attach(widget):
            if self._wheel_tag not in widget.bindtags():
                widget.bindtags((self._wheel_tag, *widget.bindtags()))
            for child in widget.winfo_children():
                attach(child)
        attach(self.content)
        self.canvas.bindtags((self._wheel_tag, *self.canvas.bindtags()))

    def _mousewheel(self, event):
        if not event.delta:
            return
        units = -int(event.delta / 120) if abs(event.delta) >= 120 else (-1 if event.delta > 0 else 1)
        if event.state & 1:  # Shift + wheel for a screen narrower than the form.
            self.canvas.xview_scroll(units, 'units')
        else:
            self.canvas.yview_scroll(units, 'units')
        return 'break'

    def _cleanup(self, event):
        if event.widget is self:
            self.unbind_class(self._wheel_tag, '<MouseWheel>')
