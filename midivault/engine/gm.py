"""General MIDI program names and small shared helpers."""

GM_PROGRAM_NAMES = [
    "Acoustic Grand Piano", "Bright Acoustic Piano", "Electric Grand Piano",
    "Honky-tonk Piano", "Electric Piano 1", "Electric Piano 2", "Harpsichord",
    "Clavinet", "Celesta", "Glockenspiel", "Music Box", "Vibraphone",
    "Marimba", "Xylophone", "Tubular Bells", "Dulcimer", "Drawbar Organ",
    "Percussive Organ", "Rock Organ", "Church Organ", "Reed Organ",
    "Accordion", "Harmonica", "Tango Accordion", "Acoustic Guitar (nylon)",
    "Acoustic Guitar (steel)", "Electric Guitar (jazz)",
    "Electric Guitar (clean)", "Electric Guitar (muted)", "Overdriven Guitar",
    "Distortion Guitar", "Guitar Harmonics", "Acoustic Bass",
    "Electric Bass (finger)", "Electric Bass (pick)", "Fretless Bass",
    "Slap Bass 1", "Slap Bass 2", "Synth Bass 1", "Synth Bass 2", "Violin",
    "Viola", "Cello", "Contrabass", "Tremolo Strings", "Pizzicato Strings",
    "Orchestral Harp", "Timpani", "String Ensemble 1", "String Ensemble 2",
    "SynthStrings 1", "SynthStrings 2", "Choir Aahs", "Voice Oohs",
    "Synth Voice", "Orchestra Hit", "Trumpet", "Trombone", "Tuba",
    "Muted Trumpet", "French Horn", "Brass Section", "SynthBrass 1",
    "SynthBrass 2", "Soprano Sax", "Alto Sax", "Tenor Sax", "Baritone Sax",
    "Oboe", "English Horn", "Bassoon", "Clarinet", "Piccolo", "Flute",
    "Recorder", "Pan Flute", "Blown Bottle", "Shakuhachi", "Whistle",
    "Ocarina", "Lead 1 (square)", "Lead 2 (sawtooth)", "Lead 3 (calliope)",
    "Lead 4 (chiff)", "Lead 5 (charang)", "Lead 6 (voice)",
    "Lead 7 (fifths)", "Lead 8 (bass + lead)", "Pad 1 (new age)",
    "Pad 2 (warm)", "Pad 3 (polysynth)", "Pad 4 (choir)", "Pad 5 (bowed)",
    "Pad 6 (metallic)", "Pad 7 (halo)", "Pad 8 (sweep)", "FX 1 (rain)",
    "FX 2 (soundtrack)", "FX 3 (crystal)", "FX 4 (atmosphere)",
    "FX 5 (brightness)", "FX 6 (goblins)", "FX 7 (echoes)", "FX 8 (sci-fi)",
    "Sitar", "Banjo", "Shamisen", "Koto", "Kalimba", "Bag pipe", "Fiddle",
    "Shanai", "Tinkle Bell", "Agogo", "Steel Drums", "Woodblock",
    "Taiko Drum", "Melodic Tom", "Synth Drum", "Reverse Cymbal",
    "Guitar Fret Noise", "Breath Noise", "Seashore", "Bird Tweet",
    "Telephone Ring", "Helicopter", "Applause", "Gunshot",
]

_NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def program_name(program: int | None) -> str | None:
    if program is None or not 0 <= program < 128:
        return None
    return GM_PROGRAM_NAMES[program]


def note_name(pitch: int) -> str:
    """Use MIDI octave numbering where middle C (60) is C4."""
    pitch = int(max(0, min(127, pitch)))
    return f"{_NOTE_NAMES[pitch % 12]}{pitch // 12 - 1}"


def is_black_key(pitch: int) -> bool:
    return int(pitch) % 12 in {1, 3, 6, 8, 10}


INSTRUMENT_KEYWORDS = {
    "Drums/percussion": (
        "drum", "drums", "percussion", "perc", "kit", "kick", "snare", "hat",
        "hats", "hihat", "hi-hat", "cymbal", "crash", "ride", "tom", "toms",
        "clap", "rim", "conga", "bongo", "shaker", "tambourine", "breakbeat",
        "break", "groove", "beat", "beats", "fingerdrum", "finger drum",
    ),
    "Bass": (
        "bass", "sub", "bassline", "bass line", "808", "bass guitar",
        "upright bass", "contrabass", "low end", "low-end",
    ),
    "Piano/keys": (
        "piano", "keys", "key", "rhodes", "wurli", "wurlitzer", "organ",
        "clav", "clavinet", "electric piano", "epiano", "grand piano",
        "harpsichord", "accordion",
    ),
    "Guitar/plucked": (
        "guitar", "gtr", "pluck", "plucked", "nylon", "steel guitar",
        "mandolin", "banjo", "sitar", "harp", "lute", "ukulele",
    ),
    "Strings": (
        "strings", "string", "violin", "viola", "cello", "orchestra",
        "orchestral", "ensemble", "chamber", "quartet", "pizzicato",
    ),
    "Brass/woodwinds": (
        "brass", "trumpet", "trombone", "tuba", "horn", "french horn", "sax",
        "saxophone", "flute", "clarinet", "oboe", "bassoon", "woodwind",
        "piccolo", "recorder", "english horn",
    ),
    "Synth": (
        "synth", "synthesizer", "lead synth", "pad", "analog", "digital",
        "pluck synth", "arp synth", "supersaw", "saw", "square", "fm",
        "wavetable", "electronic", "edm", "chiptune", "vst",
    ),
}

ROLE_KEYWORDS = {
    "Drum groove": ("groove", "beat", "break", "loop", "pattern", "two step", "backbeat"),
    "Drum fill": ("fill", "fill-in", "breakdown", "turnaround"),
    "Bassline": ("bassline", "bass line", "bass riff", "bassloop"),
    "Chord progression": ("chords", "chord progression", "progression", "harmony", "comping"),
    "Lead/melody": ("lead", "melody", "melodic", "topline", "theme", "hook", "riff"),
    "Arpeggio": ("arp", "arpeggio", "arpeggiated", "broken chord"),
    "Pad/sustained harmony": ("pad", "sustain", "sustained", "ambient", "drone"),
    "Exercise or technical pattern": ("exercise", "scale", "scales", "practice", "technique", "etude", "study"),
    "Complete song or multi-part arrangement": ("song", "full arrangement", "multitrack", "multi-track", "arrangement", "mix"),
}

GENRE_HINTS = {
    "Hip-hop / lo-fi beat": ("hip hop", "hip-hop", "hiphop", "lofi", "lo-fi", "boom bap", "trap"),
    "House / techno": ("house", "techno", "club", "dance", "edm", "garage"),
    "Cinematic / ambient": ("cinematic", "ambient", "soundtrack", "score", "film", "trailer"),
    "Jazz-leaning": ("jazz", "swing", "bebop", "fusion"),
    "Rock / band": ("rock", "metal", "punk", "band"),
    "Classical / acoustic": ("classical", "baroque", "sonata", "étude", "etude", "orchestral"),
    "Funk / groove": ("funk", "groove", "soul", "disco"),
}
