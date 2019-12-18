# -*- coding: utf-8 -*-

import logging
import requests
import six
import random
import boto3



from ask_sdk_core.skill_builder import SkillBuilder
from ask_sdk_core.handler_input import HandlerInput
from ask_sdk_core.dispatch_components import (
    AbstractRequestHandler, AbstractExceptionHandler,
    AbstractResponseInterceptor, AbstractRequestInterceptor)
from ask_sdk_core.utils import is_intent_name, is_request_type

from typing import Union, Dict, Any, List
from ask_sdk_model.dialog import (
    ElicitSlotDirective, DelegateDirective)
from ask_sdk_model import (
    Response, IntentRequest, DialogState, SlotConfirmationStatus, Slot)
from ask_sdk_model.slu.entityresolution import StatusCode

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)



dynamodb = boto3.resource('dynamodb')
table    = dynamodb.Table('coinCollector')


# Request Handler classes
class LaunchRequestHandler(AbstractRequestHandler):
    """Handler for skill launch."""
    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return is_request_type("LaunchRequest")(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.info("In LaunchRequestHandler")
        speech = ('Welcome to Coin Collection! Lets check up with your collection. You can add a coin or check what coins you have.')
        reprompt = "What coin do you want to add?"
        handler_input.response_builder.speak(speech).ask(reprompt)
        return handler_input.response_builder.response


class InProgressAddCoinIntent(AbstractRequestHandler):
    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return (is_intent_name("AddCoinIntent")(handler_input)
                and handler_input.request_envelope.request.dialog_state != DialogState.COMPLETED)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.info("In InProgressAddCoinIntent")
        current_intent = handler_input.request_envelope.request.intent


        return handler_input.response_builder.add_directive(
            DelegateDirective(
                updated_intent=current_intent
            )).response


class CompletedAddCoinIntent(AbstractRequestHandler):
    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return (is_intent_name("AddCoinIntent")(handler_input)
            and handler_input.request_envelope.request.dialog_state == DialogState.COMPLETED)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.info("In CompletedAddCoinIntent")
        filled_slots = handler_input.request_envelope.request.intent.slots
        user_id = handler_input.request_envelope.session.user.user_id
        slot_values = get_slot_values(filled_slots)
        write_to_database(slot_values,user_id)

        speech = ("Adding  your "
                    "{} "
                    "{} "
                    "{} ".format(
            slot_values["year"]["resolved"],
            slot_values["city"]["resolved"],
            slot_values["coin"]["resolved"])
        )


        return handler_input.response_builder.speak(speech).response


class InProgressReadCoinIntent(AbstractRequestHandler):
    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return (is_intent_name("AddCoinIntent")(handler_input)
                and handler_input.request_envelope.request.dialog_state != DialogState.COMPLETED)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.info("In InProgressReadCoinIntent")
        current_intent = handler_input.request_envelope.request.intent

        return handler_input.response_builder.add_directive(
            DelegateDirective(
                updated_intent=current_intent
            )).response


class CompletedReadCoinIntent(AbstractRequestHandler):
    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return (is_intent_name("ReadCoinIntent")(handler_input)
            and handler_input.request_envelope.request.dialog_state == DialogState.COMPLETED)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.info("In CompletedReadCoinIntent")
        filled_slots = handler_input.request_envelope.request.intent.slots
        slot_values = get_slot_values(filled_slots)
        user_id = handler_input.request_envelope.session.user.user_id
        coins_matched = check_for_coin(slot_values, user_id)
        how_many_coins_str = str(len(coins_matched))
        how_many_coins_int = len(coins_matched)

        if how_many_coins_int == 0:
            speech = ("You don't have this coin")
        elif how_many_coins_int == 1:
            speech = ("You have " + how_many_coins_str + " coin that matched your description" )
        else:
            speech = ("You have " + how_many_coins_str +
                     " coins that matched the description given")


        return handler_input.response_builder.speak(speech).response

class InProgressDeleteCoinIntent(AbstractRequestHandler):
    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return (is_intent_name("DeleteCoinIntent")(handler_input)
                and handler_input.request_envelope.request.dialog_state != DialogState.COMPLETED)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.info("In InProgressDeleteCoinIntent")
        current_intent = handler_input.request_envelope.request.intent

        return handler_input.response_builder.add_directive(
            DelegateDirective(
                updated_intent=current_intent
            )).response        

class CompletedDeleteCoinIntent(AbstractRequestHandler):
    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return (is_intent_name("DeleteCoinIntent")(handler_input)
            and handler_input.request_envelope.request.dialog_state == DialogState.COMPLETED)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.info("In CompletedDeleteCoinIntent")
        filled_slots = handler_input.request_envelope.request.intent.slots
        slot_values = get_slot_values(filled_slots)
        user_id = handler_input.request_envelope.session.user.user_id
        delete_coins(slot_values,user_id)


        speech = "Deleting coins now, What would you like me to do next?"


        return handler_input.response_builder.speak(speech).response    



class FallbackIntentHandler(AbstractRequestHandler):
    """Handler for handling fallback intent.

     2018-May-01: AMAZON.FallackIntent is only currently available in
     en-US locale. This handler will not be triggered except in that
     locale, so it can be safely deployed for any locale."""
    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return is_intent_name("AMAZON.FallbackIntent")(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.info("In FallbackIntentHandler")
        speech = ("I'm sorry I can't help you with that.")
        reprompt = "Would you like to add a coin?"
        handler_input.response_builder.speak(speech).ask(reprompt)
        return handler_input.response_builder.response


class HelpIntentHandler(AbstractRequestHandler):
    """Handler for help intent."""
    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return is_intent_name("AMAZON.HelpIntent")(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.info("In HelpIntentHandler")
        speech = ("This is coin collecting. I can help you orgainize your coins. "
                  "You can say, Add a 2019 Denver Penny")
        reprompt = "Would you like to add a coin?"

        handler_input.response_builder.speak(speech).ask(reprompt)
        return handler_input.response_builder.response


class ExitIntentHandler(AbstractRequestHandler):
    """Single Handler for Cancel, Stop and Pause intents."""
    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return (is_intent_name("AMAZON.CancelIntent")(handler_input) or
                is_intent_name("AMAZON.StopIntent")(handler_input))

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.info("In ExitIntentHandler")
        handler_input.response_builder.speak("Goodbye! Good luck coin hunting!").set_should_end_session(
            True)
        return handler_input.response_builder.response


class SessionEndedRequestHandler(AbstractRequestHandler):
    """Handler for skill session end."""
    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return is_request_type("SessionEndedRequest")(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.info("In SessionEndedRequestHandler")
        logger.info("Session ended with reason: {}".format(
            handler_input.request_envelope.request.reason))
        return handler_input.response_builder.response

# Exception Handler classes
class CatchAllExceptionHandler(AbstractExceptionHandler):
    """Catch All Exception handler.

    This handler catches all kinds of exceptions and prints
    the stack trace on AWS Cloudwatch with the request envelope."""
    def can_handle(self, handler_input, exception):
        # type: (HandlerInput, Exception) -> bool
        return True

    def handle(self, handler_input, exception):
        # type: (HandlerInput, Exception) -> Response
        logger.error(exception, exc_info=True)

        speech = "Sorry, I can't understand the command. Please say again."
        handler_input.response_builder.speak(speech).ask(speech)
        return handler_input.response_builder.response


# Request and Response Loggers
class RequestLogger(AbstractRequestInterceptor):
    """Log the request envelope."""
    def process(self, handler_input):
        # type: (HandlerInput) -> None
        logger.info("Request Envelope: {}".format(
            handler_input.request_envelope))


class ResponseLogger(AbstractResponseInterceptor):
    """Log the response envelope."""
    def process(self, handler_input, response):
        # type: (HandlerInput, Response) -> None
        logger.info("Response: {}".format(response))


# Data
required_slots = ["coin", "year", "city"]




# Utility functions
def get_resolved_value(request, slot_name):
    """Resolve the slot name from the request using resolutions."""
    # type: (IntentRequest, str) -> Union[str, None]
    try:
        return (request.intent.slots[slot_name].resolutions.
                resolutions_per_authority[0].values[0].value.name)
    except (AttributeError, ValueError, KeyError, IndexError, TypeError) as e:
        logger.info("Couldn't resolve {} for request: {}".format(slot_name, request))
        logger.info(str(e))
        return None

def get_slot_values(filled_slots):
    """Return slot values with additional info."""
    # type: (Dict[str, Slot]) -> Dict[str, Any]
    slot_values = {}
    logger.info("Filled slots: {}".format(filled_slots))

    for key, slot_item in six.iteritems(filled_slots):
        name = slot_item.name
        try:
            status_code = slot_item.resolutions.resolutions_per_authority[0].status.code

            if status_code == StatusCode.ER_SUCCESS_MATCH:
                slot_values[name] = {
                    "synonym": slot_item.value,
                    "resolved": slot_item.resolutions.resolutions_per_authority[0].values[0].value.name,
                    "is_validated": True,
                }
            elif status_code == StatusCode.ER_SUCCESS_NO_MATCH:
                slot_values[name] = {
                    "synonym": slot_item.value,
                    "resolved": slot_item.value,
                    "is_validated": False,
                }
            else:
                pass
        except (AttributeError, ValueError, KeyError, IndexError, TypeError) as e:
            logger.info("Couldn't resolve status_code for slot item: {}".format(slot_item))
            logger.info(e)
            slot_values[name] = {
                "synonym": slot_item.value,
                "resolved": slot_item.value,
                "is_validated": False,
            }
    return slot_values

def random_phrase(str_list):
    """Return random element from list."""
    # type: List[str] -> str
    return random.choice(str_list)

def build_pet_match_options(host_name, path, port, slot_values):
    """Return options for HTTP Get call."""
    # type: (str, str, int, Dict[str, Any]) -> Dict
    print("IS this being called?")
    path_params = {
        "SSET": "canine-{}-{}-{}".format(
            slot_values["coin"]["resolved"],
            slot_values["year"]["resolved"],
            slot_values["city"]["resolved"])
    }
    if host_name[:4] != "http":
        host_name = "https://{}".format(host_name)
    url = "{}:{}{}".format(host_name, str(port), path)
    return {
        "url": url,
        "path_params": path_params
    }

def http_get(http_options):
    url = http_options["url"]
    params = http_options["path_params"]
    response = requests.get(url=url, params=params)

    if response.status_code < 200 or response.status_code >= 300:
        response.raise_for_status()

    return response.json()

def write_to_database(slot_values,user_id):

    new_coin = {"year": slot_values["year"]["resolved"],
                "city": slot_values["city"]["resolved"],
                "coin": slot_values["coin"]["resolved"]}
                        
    new_coin_collection_list = [new_coin] + coin_collection_list(user_id)


    table.put_item(
        Item={
                'userID': user_id,
                'collection': new_coin_collection_list
                    
                }
        )


    return

def coin_collection_list(user_id):
    try:
        response = table.get_item(
            Key={
                'userID': user_id
            }
        )
        coin_collection_list = response['Item']['collection']
    except:
        coin_collection_list = []
    
    return coin_collection_list

def get_search_coin_criteria(slot_values):

    year = slot_values["year"]["resolved"]
    city = slot_values["city"]["resolved"]
    coin = slot_values["coin"]["resolved"]


    get_search_coin_criteria = {"year": year, "city":city, "coin":coin}

    return get_search_coin_criteria    

def check_for_coin(slot_values,user_id):

    right_coins= []
    have_coin = False


    for coin in coin_collection_list(user_id):
        if coin.get("year") == get_search_coin_criteria(slot_values).get("year") or get_search_coin_criteria(slot_values).get("year") == None:
            if coin.get("city") == get_search_coin_criteria(slot_values).get("city") or get_search_coin_criteria(slot_values).get("city") == None:
                if coin.get("coin") == get_search_coin_criteria(slot_values).get("coin") or get_search_coin_criteria(slot_values).get("coin") == None:
                    right_coins.append(coin)
                    have_coin= True

    return right_coins

def delete_coins(slot_values,user_id):
    right_coin = check_for_coin(slot_values,user_id)
    remove_coin_collection_list = coin_collection_list(user_id)
    new_coin_collection_list = [ele for ele in remove_coin_collection_list if ele not in right_coin]
    table.put_item(
        Item={
                'userID': user_id,
                'collection': new_coin_collection_list
                    
                }
        )
    return





# Skill Builder object
sb = SkillBuilder()

# Add all request handlers to the skill.
sb.add_request_handler(LaunchRequestHandler())
#sb.add_request_handler(MythicalCreaturesHandler())
sb.add_request_handler(InProgressAddCoinIntent())
sb.add_request_handler(CompletedAddCoinIntent())
sb.add_request_handler(InProgressReadCoinIntent())
sb.add_request_handler(CompletedReadCoinIntent())
sb.add_request_handler(InProgressDeleteCoinIntent())
sb.add_request_handler(CompletedDeleteCoinIntent())
sb.add_request_handler(HelpIntentHandler())
sb.add_request_handler(FallbackIntentHandler())
sb.add_request_handler(ExitIntentHandler())
sb.add_request_handler(SessionEndedRequestHandler())

# Add exception handler to the skill.
sb.add_exception_handler(CatchAllExceptionHandler())

# Add response interceptor to the skill.
sb.add_global_request_interceptor(RequestLogger())
sb.add_global_response_interceptor(ResponseLogger())

# Expose the lambda handler to register in AWS Lambda.
lambda_handler = sb.lambda_handler()