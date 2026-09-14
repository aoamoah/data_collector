"""What each label means, shown beside the video on the annotation screen.

The definition follows the thesis (Chapter 1, Definition of Key Terms): the
fingertip is treated as a pen on paper, so writing is pen-down and every
pen-up moment, a mid-letter pause included, is not_writing. Keeping the text
here, not in the screen, means one place to change if the protocol changes,
and every source must be annotated with the same one or it cannot be pooled.
"""

# One line per label, shown next to the label picker while it is selected
LABEL_RULES = {
    "writing": "The fingertip is tracing part of a letter or digit — "
               "the pen would be on the paper.",
    "not_writing": "The pen would be lifted: a pause (even 2–3 frames), a move "
                   "between strokes or letters, rest, or a gesture.",
    "unsure": "You cannot tell whether they are writing: the hand left the "
              "frame or was hidden mid-writing, or is too blurred. Not for "
              "boundaries that are merely hard to place.",
}


def guide_html(colors: dict[str, str]) -> str:
    """The full guide as rich text; `colors` maps label -> hex, as on the strip."""
    def tag(label: str) -> str:
        return (f'<span style="background:{colors[label]}; color:white;">'
                f'&nbsp;{label}&nbsp;</span>')

    return f"""
<h3 style="margin-bottom:2px;">Labelling guide</h3>
<p style="margin-top:2px;"><b>The one rule:</b> imagine the fingertip is a pen
on paper. Frames where the pen would touch the paper are {tag('writing')}.
Frames where it would be lifted are {tag('not_writing')}.</p>

<p style="margin-bottom:2px;">{tag('writing')} <b>W</b> — forming a character</p>
<ul style="margin-top:0;">
<li>every stroke that would leave ink, including a whole letter drawn in one
movement (O, S, 2)</li>
<li>joined-up letters, when the finger runs straight from one into the next</li>
<li>retracing a stroke that belongs to the letter (back up the stem of n, h)</li>
<li>a dot or tick, even if it lasts only a few frames</li>
</ul>

<p style="margin-bottom:2px;">{tag('not_writing')} <b>N</b> — the pen is up</p>
<ul style="margin-top:0;">
<li><b>pauses</b>: the fingertip stops, however briefly, even in the middle
of a letter</li>
<li>moving between strokes (end of the stem of T across to the start of its
bar)</li>
<li>moving to the next letter or word, or back to dot an i or cross a t</li>
<li>resting, raising the hand into position, lowering it</li>
<li><b>no hand in view</b> because the person isn't writing (before they
raise it, resting in their lap, after they lower it)</li>
<li>holding the hand still in writing pose before starting or after
finishing</li>
<li>gestures and fidgets: waving, pointing around, scratching, anything that
is not forming a character</li>
</ul>

<p style="margin-bottom:2px;">{tag('unsure')} <b>U</b> — can't be judged</p>
<ul style="margin-top:0;">
<li>the hand leaves the frame, or is hidden, <i>while writing</i>, so you
cannot tell whether the writing carried on. (No hand because they're resting
is not_writing, not unsure.)</li>
<li>motion blur so heavy you cannot tell whether the fingertip is on a
stroke</li>
<li><b>not</b> for a boundary that is hard to place: pick your best frame.
Unsure frames are dropped from training and scoring, so overusing it throws
away the frames the model most needs.</li>
</ul>

<h4 style="margin-bottom:2px;">Placing boundaries</h4>
<ul style="margin-top:0;">
<li>Writing starts on the first frame the fingertip moves along the stroke and
ends on the last frame it is still on it.</li>
<li>A pause starts on the first frame the fingertip stops or leaves the
stroke.</li>
<li>Mark pauses as long as they really are. Don't widen them to make them
easier to see, and don't skip short ones.</li>
<li>Label what the person is doing, not what the skeleton shows. A frame with
no landmarks where you can see writing is still writing.</li>
</ul>

<h4 style="margin-bottom:2px;">Quick workflow</h4>
<ol style="margin-top:0;">
<li>Watch once at 1× to see what was written.</li>
<li>Mark each word as writing: <b>S</b> at its start, <b>E</b> at its end,
<b>W</b>, <b>A</b>.</li>
<li>At 0.25×, mark every pause and between-stroke move inside it as
not_writing. The newest range overwrites what it overlaps, so there is no
need to split the writing range.</li>
<li><b>Fill Gaps → not_writing</b> labels whatever is left (rest,
preparation, gestures).</li>
<li>Check the strip under the video: each pause shows as a grey notch in the
green.</li>
</ol>

<h4 style="margin-bottom:2px;">Keys</h4>
<p style="margin-top:0;"><b>Space</b> play/pause · <b>← →</b> one frame ·
<b>S</b> / <b>E</b> mark start / end · <b>W N U</b> pick label · <b>A</b> add ·
<b>Ctrl+Z</b> / <b>Ctrl+Y</b> undo / redo · <b>F1</b> show/hide this guide</p>
"""
