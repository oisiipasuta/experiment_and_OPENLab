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
LISTENING_DEVICE_LABELS.update(
    {"earphones": "イヤホン", "headphones": "ヘッドフォン"}
)
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
    "曲を聴いて、あなたの「好き」を見つける音楽プロフィール作成アプリです。"
)

MUSIC_EXPERIENCE_HELP = (
    "音楽経験とは、学校の授業以外で、継続的に音楽活動を行った経験を指します。"
    "部活動、習い事、個人練習、バンド活動、合唱、作曲、DTMなどで音楽に取り組んだ経験がある場合は"
    "音楽経験ありとして回答してください。学校の授業だけでの経験、単に音楽を聴くことが好き、"
    "ライブに行くことが多い、カラオケが好き、という場合はここでは音楽経験には含めません。"
)

EXPERIMENT_DESCRIPTION_ITEMS = [
    {
        "title": "プロフィール作成の流れ",
        "body": "操作練習の1曲のあと、5曲を聴きます。「ここ好き！」と思った場所を記録し、曲全体の印象を選ぶと、最後にあなたの音楽好みプロフィールが完成します。",
    },
    {
        "title": "一番好きだったところの確認",
        "body": "1回以上記録した曲では、一番好きだったところを1つ選び、当てはまる理由を複数選べます。自由記述はありません。",
    },
    {
        "title": "保存される情報",
        "body": "プロフィール作成に必要な属性情報、聴取環境、「ここ好き！」を押したタイミング、曲全体の印象、選んだ理由が保存されます。",
    },
    {
        "title": "参加判断",
        "body": "入力内容はプロフィール作成と研究・分析に利用されます。内容を確認し、同意できる場合のみ作成を開始してください。",
    },
]

EXPERIMENT_FLOW_STEPS = [
    "プロフィール作成に必要な基本情報を入力します。",
    "曲を1曲ずつ聴きます。",
    "曲を聴いている間に、「ここ好き！」と思ったタイミングがあればボタンを押します。何回でも押せます。好きなところがなければ押さなくても大丈夫です。",
    "1回以上押した場合は、一番好きだったところを1つ遳び、当てはまる理由を複数選びます。",
    "曲全体の印象を9項目・7段階で回答します。",
    "練習曲が終わった後、本番に入る前に、設定した音量について回答します。",
    "操作練習1曲と5曲のプロフィール作成用トラックで繰り返します。",
    "5曲の回答が終わると、あなたの音楽好みプロフィールを表示します。途中で閉じても、同じ参加者IDで続きから再開できます。",
]

EXPERIMENT_NOTES = [
    "できるだけ静かな場所で参加してください。",
    "音楽の再生は、普段音楽を聴いている環境で再生してください。イヤホンやヘッドフォンなど指定はありません。",
    "音量は、聴き取りやすく大きすぎない程度に調整してください。",
    "音量の調整は、使用しているパソコンやスマホなどデバイス側の設定を変更してください。Webサイト上の音量操作ボタンは操作しないでください。",
    "端末やイヤホンの設定でイコライザーを設定している場合は、その設定をオフにしてください。難しい場合は実験者に知らせてください。"
    "曲の再生中は、なるべく他の作業をせず、曲に集中してください。",
    "操作に迷った場合や不具合があった場合は、実験者に知らせてください。",
]

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
    {
        "value": "other",
        "label": "その他",
        "description": "上の項目以外の理由があった",
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
    *[
        {
            "file_path": f"audio/main_{index:02d}.wav",
            "duration_seconds": 12,
            "frequency_hz": 260 + index * 18,
        }
        for index in range(4, 16)
    ],
]
