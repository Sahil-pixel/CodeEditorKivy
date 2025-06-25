#Author : Sk Sahil (Sahil-pixel)

from kivy.app import App
from kivy.lang import Builder
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.codeinput import CodeInput
from kivy.uix.recycleview import RecycleView
from kivy.uix.recycleboxlayout import RecycleBoxLayout
from kivy.uix.button import Button
from kivy.metrics import dp
from kivy.clock import Clock
from kivy.core.window import Window
from pygments.lexers import PythonLexer
import jedi
import re

# ──────────────────────────────────────
# Kivy UI Layout using KV Language
# ──────────────────────────────────────
KV = '''
<EditorRoot>:
    orientation: 'vertical'

    # Top bar with buttons like a toolbar
    BoxLayout:
        size_hint_y: None
        height: dp(48)
        padding: dp(8)
        spacing: dp(8)
        canvas.before:
            Color:
                rgba: 0.1, 0.3, 0.6, 1
            Rectangle:
                pos: self.pos
                size: self.size
        Button:
            text: 'New'
            on_release: root.code_input.text = ""
        Button:
            text: 'Open'
        Button:
            text: 'Save'
        Button:
            text: 'Run'

    # ScrollView contains code area and line numbers
    ScrollView:
        id: scroll
        do_scroll_x: False
        do_scroll_y: True
        bar_width: dp(10)
        BoxLayout:
            id: editor_container
            orientation: 'horizontal'
            size_hint_y: None
            height: self.minimum_height

            # Line numbers on the left
            LineNumberInput:
                id: line_input
                size_hint_x: None
                width: dp(40)
                readonly: True
                font_size: root.font_size
                background_color: root.bg_color
                foreground_color: root.line_color
                cursor_width: 0

            # Main code editor with syntax highlighting
            CodeInput:
                id: code_input
                font_size: root.font_size
                lexer: root.lexer
                size_hint_y: None
                height: self.minimum_height
                background_color: root.bg_color
                foreground_color: (0, 0, 0, 1)
                cursor_blink: True
                use_handles: False
                use_bubble: True
                unfocus_on_touch: False

<SuggestionButton@Button>:
    size_hint_y: None
    height: dp(30)

<SuggestionPopup@BoxLayout>:
    orientation: 'vertical'
    size_hint: None, None
    size: dp(200), dp(150)
    opacity: 0
    pos: 0, 0
    RecycleView:
        id: rv
        viewclass: 'SuggestionButton'
        size_hint: 1, 1
        RecycleBoxLayout:
            orientation: 'vertical'
            default_size: None, dp(30)
            default_size_hint: 1, None
            size_hint_y: None
            height: self.minimum_height
'''

Builder.load_string(KV)

# ──────────────────────────────────────
# Code Input for Line Numbers
# ──────────────────────────────────────
class LineNumberInput(CodeInput):
    pass

# ──────────────────────────────────────
# Suggestion Popup Overlay
# ──────────────────────────────────────
class SuggestionPopup(BoxLayout):
    def show(self, suggestions, insert_callback, pos):
        self.ids.rv.data = [{
            'text': s,
            'on_release': lambda s=s: insert_callback(s)
        } for s in suggestions]
        self.pos = pos
        self.opacity = 1
        self.visible = True

    def hide(self):
        self.opacity = 0
        self.visible = False

# ──────────────────────────────────────
# Main Editor Widget
# ──────────────────────────────────────
class EditorRoot(BoxLayout):
    def __init__(self, **kwargs):
        self.lexer = PythonLexer()
        self.line_color = (0.2, 0.2, 0.8, 1)
        self.bg_color = (0.9, 0.95, 1, 1)
        self.font_size = dp(16)
        super().__init__(**kwargs)
        Clock.schedule_once(self._post_init)

    def _post_init(self, dt):
        # Setup references
        self.code_input = self.ids.code_input
        self.line_input = self.ids.line_input
        self.scroll = self.ids.scroll

        # Suggestion popup
        self.suggestion_popup = SuggestionPopup()
        App.get_running_app().root.add_widget(self.suggestion_popup)

        # Events
        self.code_input.bind(text=self.on_text_changed, cursor=self.on_cursor_move)
        self.code_input.bind(scroll_y=self.sync_scroll)
        self.scroll.bind(scroll_y=self.sync_scroll_back)
        Clock.schedule_interval(self.update_line_numbers, 0.1)

        # Patch insert_text to only trigger suggestions when typing real words
        original_insert = self.code_input.insert_text

        def custom_insert(text, from_undo=False):
            result = original_insert(text, from_undo)

            # ──────────────────────────────────────────────
            # Prevent showing suggestions on ENTER, SPACE
            # Only show if typed word-like character
            # ──────────────────────────────────────────────
            if re.match(r'[a-zA-Z0-9_.]', text):
                Clock.unschedule(self.update_suggestions)
                Clock.schedule_once(self.update_suggestions, 0.2)
            else:
                self.suggestion_popup.hide()

            return result

        self.code_input.insert_text = custom_insert

    def on_text_changed(self, *args):
        self.update_line_numbers(0)

    def update_line_numbers(self, dt):
        lines = self.code_input.text.split('\n')
        visual_lines = []
        font_px = self.font_size * 0.6
        wrap_width = max(1, int(self.code_input.width / font_px))

        for i, line in enumerate(lines):
            visual_lines.append(str(i + 1))
            wraps = len(line) // wrap_width
            visual_lines.extend([""] * wraps)

        self.line_input.text = '\n'.join(visual_lines)
        self.line_input.height = self.code_input.height

    def sync_scroll(self, instance, value):
        self.line_input.scroll_y = value

    def sync_scroll_back(self, instance, value):
        self.code_input.scroll_y = value
        self.line_input.scroll_y = value

    def get_current_word(self):
        # Get current word fragment before cursor (e.g. "os.pat")
        before_cursor = self.code_input.text[:self.code_input.cursor_index()]
        match = re.search(r'([\w\.]+)$', before_cursor)
        return match.group(1) if match else ""

    def insert_completion(self, completion):
        # Replace last part of word with full suggestion
        full_word = self.get_current_word()
        if full_word:
            last_dot = full_word.rfind('.')
            partial = full_word[last_dot + 1:] if last_dot != -1 else full_word
            i = self.code_input.cursor_index()
            self.code_input.text = self.code_input.text[:i - len(partial)] + self.code_input.text[i:]
            self.code_input.cursor = self.code_input.get_cursor_from_index(i - len(partial))
        self.code_input.insert_text(completion)
        self.suggestion_popup.hide()
        self.code_input.focus = True

    def on_cursor_move(self, *args):
        Clock.unschedule(self.update_suggestions)
        Clock.schedule_once(self.update_suggestions, 0.2)

    def update_suggestions(self, dt):
        current_word = self.get_current_word()

        # ──────────────────────────────────────────────
        #  Hide suggestions if cursor is at whitespace or empty
        # ──────────────────────────────────────────────
        if not current_word or current_word.strip() == "":
            self.suggestion_popup.hide()
            return

        try:
            script = jedi.Script(self.code_input.text, path='main.py')
            index = self.code_input.cursor_index()
            line = self.code_input.text[:index].count('\n') + 1
            column = index - self.code_input.text.rfind('\n', 0, index) - 1
            completions = script.complete(line, column)
            names = [c.name for c in completions]
        except Exception:
            names = []

        if names:
            self.show_suggestions(names)
        else:
            self.suggestion_popup.hide()

    def show_suggestions(self, names):
        # Clamp popup inside screen
        x, y = self.code_input.cursor_pos
        win_x, win_y = self.code_input.to_window(x, y)
        popup_w = dp(200)
        popup_h = dp(150)
        pos_x = max(dp(5), min(win_x + dp(40), Window.width - popup_w - dp(5)))
        pos_y = max(dp(5), min(win_y - popup_h - dp(20), Window.height - popup_h - dp(5)))

        self.suggestion_popup.show(
            suggestions=names,
            insert_callback=self.insert_completion,
            pos=(pos_x, pos_y)
        )


class KivyCodeEditorApp(App):
    def build(self):
        return EditorRoot()


if __name__ == '__main__':
    KivyCodeEditorApp().run()
