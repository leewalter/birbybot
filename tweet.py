#!/usr/bin/env python
# -*- coding: utf-8 -*-

import datetime
import logging
import os
import pathlib
import random

from dateutil.relativedelta import relativedelta
from flickrapi import shorturl
from google.cloud import datastore
from twython import Twython

import utils
from classify_images import download_image
from flickr_to_datastore import write_entities_to_datastore

### LOGGING ####################################################################
logger = logging.getLogger(__name__)
utils.configure_logger(logger, console_output=True)
################################################################################

def pull_entities_from_datastore(ds_client, tweeted_before=None):
    """Retrieve bird photos that haven't been tweeted recently.
    
    Args:
        tweeted_before (datetime.datetime)

    Returns:
        entities (list): List of is_bird Photo entities from beachbirbys
        datastore, tweeted before datetime if passed. E.g., [<Entity('Photo',
        'Flickr-36092472285') {'source': 'Flickr', ...}, ...]
    """
    logger.info(f"Retrieving is_bird entities tweeted before {tweeted_before:%Y-%m-%d}...")
    query = ds_client.query(kind="Photo")
    query.add_filter("is_bird", "=", True)
    if tweeted_before:
        query.add_filter("last_tweeted", "<=", tweeted_before)
    logger.debug(query)
    entities = list(query.fetch())
    logger.info(f"Retrieved {len(entities)} entities.")
    logger.debug(entities)
    return entities


def create_message(entity):
    """Takes Photo entity and returns message string."""
    title = entity.get("title")
    photographer = entity.get("ownername")
    shortlink = shorturl.url(entity.get("id"))
    message = f"{title} by {photographer} {shortlink} #birbybot"
    logger.debug(message)
    return message


def tweet_photo(message, filepath):
    try:
        twitter = Twython(
            os.environ['TWITTER_CONSUMER_KEY'],
            os.environ['TWITTER_CONSUMER_SECRET'],
            os.environ['TWITTER_ACCESS_TOKEN'],
            os.environ['TWITTER_ACCESS_SECRET']
        )
    except KeyError as e:
        logger.exception(e)
        raise
    img = open(filepath, 'rb')
    try:
        response = twitter.upload_media(media=img)
        logger.debug(response)
        r = twitter.update_status(status=message, media_ids=[response['media_id']])
        logger.info(r)
        return r
    except Exception as e:
        logger.exception(e)
        raise


def tweet_and_update(ds_client, entity):
    logger.info(f"Tweeting {entity.key.name}...")
    logger.debug(entity)
    message = create_message(entity)
    filepath = os.path.join(os.path.dirname(__file__), f'assets/{entity.key.name}.jpg')
    if not pathlib.Path(filepath).exists():
        filepath = download_image(url=entity.get("download_url"),
                                    filename=entity.key.name)
    r = tweet_photo(message, filepath)
    # TODO: Parse r['created_at'] and use that for last tweeted?
    entity.update({
        "last_tweeted": datetime.datetime.utcnow(),
        "entity_updated": datetime.datetime.utcnow()
    })
    write_entities_to_datastore(ds_client, [entity])
    return

################################################################################

if __name__ == "__main__":
    try:
        ds_client = datastore.Client()
        one_month_ago = datetime.datetime.utcnow() - relativedelta(months=1)
        entities = pull_entities_from_datastore(ds_client, tweeted_before=one_month_ago)
        tweet_and_update(ds_client, random.choice(entities))
    except Exception as e:
        logger.exception(e)
