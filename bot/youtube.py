def video_exists(video_id: str, playlist_id: str) -> bool:
    service = _get_service()
    page_token = ""
    while True:
        res = service.playlistItems().list(
            part="contentDetails",
            playlistId=playlist_id,
            maxResults=50,
            pageToken=page_token
        ).execute()
        if any(it["contentDetails"]["videoId"] == video_id for it in res["items"]):
            return True
        page_token = res.get("nextPageToken")
        if not page_token:
            break
    return False
