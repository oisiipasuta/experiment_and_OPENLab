SD_ITEMS = [
    {"name": "bright_dark", "left": "明るい", "right": "暗い"},
    {"name": "smooth_rough", "left": "滑らかな", "right": "荒い"},
    {"name": "rich_thin", "left": "豊かな", "right": "痩せた"},
    {"name": "clear_muddy", "left": "澄んだ", "right": "濁った"},
    {"name": "intense_calm", "left": "激しい", "right": "穏やかな"},
    {"name": "heavy_light", "left": "重い", "right": "軽い"},
    {"name": "soft_hard", "left": "柔らかい", "right": "硬い"},
    {"name": "thick_thin", "left": "厚い", "right": "薄い"},
    {"name": "like_dislike", "left": "好き", "right": "嫌い"},
]

GENDER_OPTIONS = [
    {"value": "female", "label": "女性"},
    {"value": "male", "label": "男性"},
    {"value": "other", "label": "その他"},
    {"value": "no_answer", "label": "回答しない"},
]

MUSIC_EXPERIENCE_OPTIONS = [
    {"value": "yes", "label": "経験あり"},
    {"value": "no", "label": "経験なし"},
    {"value": "no_answer", "label": "回答しない"},
]

MUSIC_EXPERIENCE_TYPE_OPTIONS = [
    {"value": "instrument", "label": "楽器演奏"},
    {"value": "vocal", "label": "歌唱・合唱"},
    {"value": "band_or_ensemble", "label": "バンド・吹奏楽・アンサンブル"},
    {"value": "composition", "label": "作曲・編曲"},
    {"value": "dtm", "label": "DTM・音楽制作"},
    {"value": "other", "label": "その他"},
]

LISTENING_DEVICE_OPTIONS = [
    {"value": "wired_earphones", "label": "有線イヤホン"},
    {"value": "wireless_earphones", "label": "無線イヤホン"},
    {"value": "wired_headphones", "label": "有線ヘッドフォン"},
    {"value": "wireless_headphones", "label": "無線ヘッドフォン"},
    {"value": "speaker", "label": "スピーカー"},
    {"value": "other", "label": "その他"},
]

LISTENING_ENVIRONMENT_OPTIONS = [
    {"value": "mac", "label": "Mac"},
    {"value": "windows", "label": "Windows"},
    {"value": "iphone", "label": "iPhone"},
    {"value": "ipad", "label": "iPad"},
    {"value": "android", "label": "Android"},
    {"value": "other", "label": "その他"},
]

EXPERIMENT_BROWSER_OPTIONS = [
    {"value": "chrome", "label": "Chrome"},
    {"value": "safari", "label": "Safari"},
    {"value": "other", "label": "その他"},
]

VOLUME_IMPRESSION_OPTIONS = [
    {"value": "too_quiet", "label": "小さすぎる"},
    {"value": "slightly_quiet", "label": "やや小さい"},
    {"value": "comfortable", "label": "ちょうどよい"},
    {"value": "slightly_loud", "label": "やや大きい"},
    {"value": "too_loud", "label": "大きすぎる"},
]

GENDER_LABELS = {item["value"]: item["label"] for item in GENDER_OPTIONS}
MUSIC_EXPERIENCE_LABELS = {
    item["value"]: item["label"] for item in MUSIC_EXPERIENCE_OPTIONS
}
MUSIC_EXPERIENCE_LABELS.update(
    {
        "none": "経験なし",
        "beginner": "少し経験あり",
        "intermediate": "継続的な経験あり",
        "advanced": "専門的な経験あり",
    }
)
MUSIC_EXPERIENCE_TYPE_LABELS = {
    item["value"]: item["label"] for item in MUSIC_EXPERIENCE_TYPE_OPTIONS
}
LISTENING_DEVICE_LABELS = {
    item["value"]: item["label"] for item in LISTENING_DEVICE_OPTIONS
}
LISTENING_ENVIRONMENT_LABELS = {
    item["value"]: item["label"] for item in LISTENING_ENVIRONMENT_OPTIONS
}
EXPERIMENT_BROWSER_LABELS = {
    item["value"]: item["label"] for item in EXPERIMENT_BROWSER_OPTIONS
}
VOLUME_IMPRESSION_LABELS = {
    item["value"]: item["label"] for item in VOLUME_IMPRESSION_OPTIONS
}

PILOT_NOTICE = (
    "このWebアプリは現在、ゼミ内でのパイロット運用中です。"
    "操作のわかりにくい点や不具合があれば、実験者にお知らせください。"
)

MUSIC_EXPERIENCE_HELP = (
    "音楽経験とは、学校の授業以外で、継続的に音楽活動を行った経験を指します。"
    "部活動、習い事、個人練習、バンド活動、合唱、作曲、DTMなどで音楽に取り組んだ経験がある場合は"
    "音楽経験ありとして回答してください。学校の授業だけでの経験、単に音楽を聴くことが好き、"
    "ライブに行くことが多い、カラオケが好き、という場合はここでは音楽経験には含めません。"
)

EXPERIMENT_DESCRIPTION_ITEMS = [
    {
        "title": "実験の流れ",
        "body": "曲を聴いている間に良いと感じたタイミングを記録し、曲が終わったあとに曲全体をどのように感じたか回答します。",
    },
    {
        "title": "良いと感じた部分の確認",
        "body": "記録された部分は、1 件でも複数件でも、曲全体についての回答後に理由とあわせて確認します。",
    },
    {
        "title": "保存される情報",
        "body": "参加者ID、属性情報、聴取環境、ブラウザ、使用機器、音量確認、参加同意、ボタン押下時刻、曲の評定、選択理由、品質確認、再生・画面離脱に関する操作記録が保存されます。CloudWorksワーカーIDそのものは保存しません。",
    },
    {
        "title": "参加判断",
        "body": "入力内容は研究・分析目的で利用されます。内容を確認し、同意できる場合のみ実験を開始してください。",
    },
]

EXPERIMENT_FLOW_STEPS = [
    "参加者情報を入力します。",
    "曲を1曲ずつ聴きます。",
    "曲を聴いている間に、「好きだ」と感じたタイミングがあればボタンを押します。",
    "曲が終わった後、その曲全体の印象について回答します。",
    "曲全体の印象を回答後、1つ以上ボタンを押している場合は最も「好きだ」と感じた部分を選択します。加えて、最も「好きだ」と感じた部分の選択理由を複数項目から選びます。",
    "練習曲が終わった後、本番に入る前に、設定した音量について回答します。",
    "これを合計30曲それぞれで繰り返します。",
    "所要時間は約1時間20分を想定しています。途中休憩は適宜取ってください。一度サイトを閉じた場合は途中から始められるようになっています。",
]

EXPERIMENT_NOTES = [
    "できるだけ静かな場所で参加してください。",
    "音楽の再生は、普段音楽を聴いている環境で再生してください。イヤホンやヘッドフォンなど指定はありません。",
    "音量は、聴き取りやすく大きすぎない程度に調整してください。",
    "音量の調整は、使用しているパソコンやスマホなどデバイス側の設定を変更してください。Webサイト上の音量操作ボタンは操作しないでください。",
    "端末やイヤホンの設定でイコライザーを設定している場合は、その設定をオフにしてください。難しい場合は実験者に知らせてください。",
    "曲の再生中は、なるべく他の作業をせず、曲に集中してください。",
    "操作に迷った場合や不具合があった場合は、実験者に知らせてください。",
]

ATTENTION_CHECK_PROMPT = (
    "回答内容を確認するための項目です。この項目では必ず「5」を選択してください。"
)
ATTENTION_CHECK_EXPECTED_VALUE = 5
ATTENTION_CHECK_VERSION = "rating_instruction_5_v1"

SELECTION_REASON_OPTIONS = [
    {
        "value": "melody",
        "label": "メロディが心地よかった",
        "description": "旋律の流れやフレーズが好ましく感じられた",
    },
    {
        "value": "rhythm",
        "label": "リズムが心地よかった",
        "description": "リズムのノリや繰り返しが気持ちよく感じられた",
    },
    {
        "value": "timbre",
        "label": "音色が好みだった",
        "description": "楽器や音の響き方に魅力を感じた",
    },
    {
        "value": "harmony",
        "label": "音の重なりや響きが良かった",
        "description": "複数の音の重なり方や雰囲気が好ましく感じられた",
    },
    {
        "value": "build",
        "label": "展開が印象的だった",
        "description": "変化や推移が魅力的に感じられた",
    },
    {
        "value": "emotion",
        "label": "感情的に強く惹かれた",
        "description": "気分や感情が大きく動いたと感じた",
    },
    {
        "value": "stability",
        "label": "落ち着きや安定感があった",
        "description": "自然で聴きやすく、安心感があった",
    },
    {
        "value": "novelty",
        "label": "意外性や新鮮さがあった",
        "description": "予想外の変化や独自性に魅力を感じた",
    },
]

SUPPORTED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg"}

SAMPLE_SONGS = [
    {
        "file_path": "audio/practice_01.wav",
        "duration_seconds": 10,
        "frequency_hz": 440,
    },
    {
        "file_path": "audio/practice_02.wav",
        "duration_seconds": 10,
        "frequency_hz": 523,
    },
    {
        "file_path": "audio/main_01.wav",
        "duration_seconds": 12,
        "frequency_hz": 330,
    },
    {
        "file_path": "audio/main_02.wav",
        "duration_seconds": 12,
        "frequency_hz": 392,
    },
    {
        "file_path": "audio/main_03.wav",
        "duration_seconds": 12,
        "frequency_hz": 494,
    },
]
