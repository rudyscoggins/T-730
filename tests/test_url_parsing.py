from bot.youtube.urls import canonical_video_ids_from_text


def test_extracts_from_multiple_variants_and_deduplicates():
    text = (
        "check these: "
        "https://youtu.be/AAAAAAA1111?t=30 "
        "https://www.youtube.com/watch?v=BBBBBBB2222&ab_channel=test "
        "https://m.youtube.com/shorts/CCCCCCC3333 "
        "https://www.youtube.com/embed/DDDDDDD4444?start=10 "
        "https://www.youtube.com/v/EEEEEEE5555#t=1m "
        "dup: https://youtube.com/watch?v=BBBBBBB2222&feature=share "
        "and live: https://www.youtube.com/live/FFFFFFF6666?si=xyz"
    )

    ids = canonical_video_ids_from_text(text)
    assert ids == [
        "AAAAAAA1111",
        "BBBBBBB2222",
        "CCCCCCC3333",
        "DDDDDDD4444",
        "EEEEEEE5555",
        "FFFFFFF6666",
    ]

