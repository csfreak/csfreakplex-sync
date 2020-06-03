import logging
import os
import subprocess
import configparser
from plexapi.server import PlexServer
from plexapi.exceptions import BadRequest
from plexapi import utils as plexutils

config = configparser.ConfigParser()
config.read('.config')

server = PlexServer(config['PLEX']['RemoteURI'], config['PLEX']['Token'])
local_server = PlexServer(config['PLEX']['LocalURI'], config['PLEX']['Token'])


def get_media_title(media):
    if media.TYPE == 'episode':
        return get_episode_title(media)
    return media.title


def get_episode_title(episode):
    return "{}-{}-{}".format(
        episode.show().title,
        episode.season().title,
        episode.title
    )


def optimize(media):
    for version in media.media:
        if version.target == 'Optimized for Mobile':
            return "Ready"
    try:
        media.optimize(targetTagID=1)
        logging.info("Queued {}".format(get_media_title(media)))
        return "Queued"
    except BadRequest:
        logging.warn('unable to optimize {}.  Already Exists'.format(get_media_title(media)))
        return "Queued"
    except Exception:
        logging.error('unable to optimize {}.'.format(get_media_title(media)))
        return None


def get_taged_media(tag=config['PLEX']['MOBILE_LABEL_ID']):
    return_media = []
    for media in server.library.search(label=tag):
        if media.TYPE == 'show':
            for episode in media.episodes():
                return_media.append(episode)
        elif media.TYPE == 'movie':
            return_media.append(media)
    return return_media


def get_local_media_titles():
    return_media_titles = []
    for media in local_server.library.all():
        if media.TYPE == 'movie':
            return_media_titles.append(media.title)
        elif media.TYPE == 'show':
            for episode in media.episodes():
                return_media_titles.append(get_episode_title(episode))
    return return_media_titles


def download_media(media):
    savepath = get_file_save_path(media)
    os.makedirs(savepath, mode=0o777, exist_ok=True)
    logging.info("Downloading {} to {}".format(get_media_title(media), savepath))
    # modified from plexapi.base.playable
    location = [i for i in media.iterParts() if i and i.optimizedForStreaming][0]
    filename = '%s.%s' % (media._prettyfilename(), location.container)
    download_url = media._server.url('%s?download=1' % location.key)
    return plexutils.download(
        download_url, media._server._token, filename=filename,
        savepath=savepath, session=media._server._session)


def get_file_save_path(media):
    if media.TYPE == 'movie':
        return os.path.join(config['MEDIA']['MEDIA_ROOT'], config['MEDIA']['MOVIE_ROOT'], get_movie_dir_name(media))
    elif media.TYPE == 'episode':
        return os.path.join(config['MEDIA']['MEDIA_ROOT'],
                            config['MEDIA']['TV_ROOT'],
                            get_show_dir_name(media),
                            get_season_dir_name(media))


def get_movie_dir_name(movie):
    return "{} ({})".format(movie.title, movie.year)


def get_season_dir_name(episode):
    return episode.season().title.replace(' ', '.')


def get_show_dir_name(episode):
    return episode.show().title


def check_network():
    result = dict()
    for item in subprocess.run(['wpa_cli', '-iwlan0', 'status'], capture_output=True).stdout.decode('utf8').split('\n'):
        if '=' in item:
            result[item.split('=')[0]] = item.split('=', maxsplit=1)[1]
    if result.get('ssid') == 'thelastresort' and result.get('wpa_state') == 'COMPLETED':
        return True
    else:
        logging.error(result)
    return False


if __name__ == '__main__':
    if not check_network():
        logging.error("Not on HOME NETWORK")
        exit(1)
    local_titles = get_local_media_titles()
    for media in get_taged_media():
        if get_media_title(media) not in local_titles:
            status = optimize(media)
            if status == "Ready":
                download_media(media)
    for library in local_server.library.sections():
        library.update()
