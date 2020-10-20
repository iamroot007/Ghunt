import httpx
import json
import urllib.parse
from PIL import Image
from lib.utils import *
from lib.search import search as gdoc_search
from pprint import pprint
from io import BytesIO


def youtube_channel_search(client, query):
    link = "https://www.youtube.com/results?search_query={}&sp=EgIQAg%253D%253D"
    req = client.get(link.format(urllib.parse.quote(query)))
    source = req.text
    data = json.loads(source.split('window["ytInitialData"] = ')[1].split('window["ytInitialPlayerResponse"]')[0].split(';\n')[0])
    channels = data["contents"]["twoColumnSearchResultsRenderer"]["primaryContents"]["sectionListRenderer"]["contents"][0]["itemSectionRenderer"]["contents"]
    results = {"channels": [], "length": len(channels)}
    try:
        for channel in channels:
            if len(results["channels"]) >= 10:
                break
            title = channel["channelRenderer"]["title"]["simpleText"]
            if not query.lower() in title.lower():
                continue
            avatar_link = channel["channelRenderer"]["thumbnail"]["thumbnails"][0]["url"].split('=')[0]
            if avatar_link[:2] == "//":
                avatar_link = "https:"+avatar_link
            profil_url = "https://youtube.com" + channel["channelRenderer"]["navigationEndpoint"]["browseEndpoint"]["canonicalBaseUrl"]
            req = client.get(avatar_link)
            img = Image.open(BytesIO(req.content))
            hash = image_hash(img)
            results["channels"].append({"profil_url": profil_url, "name": title, "hash": hash})
        return results
    except KeyError:
        return False

def youtube_channel_search_gdocs(client, query, cfg):
    search_query = f"site:youtube.com/channel \\\"{query}\\\""
    search_results = gdoc_search(search_query, cfg)
    channels = []
    for result in search_results:
        sanitized  = "https://youtube.com/"+('/'.join(result["link"].split('/')[3:5]))
        if sanitized not in channels:
            channels.append(sanitized)

    if not channels:
        return False
    results = {"channels": [], "length": len(channels)}
    channels = channels[:5]
    for profil_url in channels:
        req = client.get(profil_url)
        source = req.text

        data = json.loads(source.split('window["ytInitialData"] = ')[1].split('window["ytInitialPlayerResponse"]')[0].split(';\n')[0])
        avatar_link = data["metadata"]["channelMetadataRenderer"]["avatar"]["thumbnails"][0]["url"].split('=')[0]
        req = client.get(avatar_link)
        img = Image.open(BytesIO(req.content))
        hash = image_hash(img)
        title = data["metadata"]["channelMetadataRenderer"]["title"]
        results["channels"].append({"profil_url": profil_url, "name": title, "hash": hash})
    return results

def get_channels(client, query, cfg):
    from_youtube = youtube_channel_search(client, query)
    from_gdocs = youtube_channel_search_gdocs(client, query, cfg)
    to_process = []
    if from_youtube:
        from_youtube["origin"] = "youtube"
        to_process.append(from_youtube)
    if from_gdocs:
        from_gdocs["origin"] = "gdocs"
        to_process.append(from_gdocs)
    if not to_process:
        return False
    return to_process

def get_confidence(data, query, hash):
    score_steps = 4

    for source_nb, source in enumerate(data):
        for channel_nb, channel in enumerate(source["channels"]):
            score = 0

            if hash == channel["hash"]:
                score += score_steps*4
            if query == channel["name"]:
                score += score_steps*3
            if query in channel["name"]:
                score += score_steps*2
            if ((source["origin"] == "youtube" and source["length"] <= 5) or
                (source["origin"] == "google" and source["length"] <= 4)):
                score += score_steps
            data[source_nb]["channels"][channel_nb]["score"] = score

    channels = []
    for source in data:
        for channel in source["channels"]:
            found_better = False
            for source2 in data:
                for channel2 in source["channels"]:
                    if channel["profil_url"] == channel2["profil_url"]:
                        if channel2["score"] > channel["score"]:
                            found_better = True
                            break
                if found_better:
                    break
            if found_better:
                continue
            else:
                channels.append(channel)
    channels = sorted([json.loads(chan) for chan in set([json.dumps(channel) for channel in channels])], key=lambda k: k['score'], reverse=True)
    panels = sorted(set([c["score"] for c in channels]), reverse=True)
    if panels and panels[0] <= 0:
        return 0, []

    maxscore = sum([p*score_steps for p in range(1,score_steps+1)])
    for panel in panels:
        chans = [c for c in channels if c["score"] == panel]
        if len(chans) > 1:
            panel-=5
        return (panel/maxscore*100), chans

def extract_usernames(channels):
    return [chan['profil_url'].split("/user/")[1] for chan in channels if "/user/" in chan['profil_url']]