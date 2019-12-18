  
# -*- coding: utf-8 -*-
import random
import six
import logging
import boto3

from typing import Union, List

from ask_sdk.standard import StandardSkillBuilder
from ask_sdk_core.dispatch_components import (
    AbstractRequestHandler, AbstractExceptionHandler,
    AbstractRequestInterceptor, AbstractResponseInterceptor)
from ask_sdk_core.handler_input import HandlerInput
from ask_sdk_core.utils import is_request_type, is_intent_name

from ask_sdk_model.dialog import (
    ElicitSlotDirective, DelegateDirective)
from ask_sdk_model import (
    Response, IntentRequest, DialogState, SlotConfirmationStatus, Slot)
from ask_sdk_model.slu.entityresolution import StatusCode

from ask_sdk_model.services.monetization import (
    EntitledState, PurchasableState, InSkillProductsResponse, Error,
    InSkillProduct)
from ask_sdk_model.interfaces.monetization.v1 import PurchaseResult
from ask_sdk_model import Response, IntentRequest
from ask_sdk_model.interfaces.connections import SendRequestDirective

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

dynamodb = boto3.resource('dynamodb')
table    = dynamodb.Table('coinCollector')

previous_intent = None
denomination = None
city = None
year = None
condition = None


# Utility functions

def get_all_entitled_products(in_skill_product_list):
    """Get list of in-skill products in ENTITLED state."""
    # type: (List[InSkillProduct]) -> List[InSkillProduct]
    entitled_product_list = [
        l for l in in_skill_product_list if (
                l.entitled == EntitledState.ENTITLED)]
    return entitled_product_list

def get_random_from_list(facts):
    """Return the fact message from randomly chosen list element."""
    # type: (List) -> str
    fact_item = random.choice(facts)
    return fact_item.get("fact")

def get_random_yes_no_question():
    """Return random question for YES/NO answering."""
    # type: () -> str
    questions = [
        "Would you like to add another coin?", "Can I tell you another fact?",
        "Do you want to hear another fact?"]
    return random.choice(questions)

def get_random_goodbye():
    """Return random goodbye message."""
    # type: () -> str
    goodbyes = ["OK.  Goodbye!", "Have a great day!", "Come back again soon!", "Good Luck Coin Hunting!"]
    return random.choice(goodbyes)

def get_speakable_list_of_products(entitled_products_list):
    """Return product list in speakable form."""
    # type: (List[InSkillProduct]) -> str
    product_names = [item.name for item in entitled_products_list]
    if len(product_names) > 1:
        # If more than one, add and 'and' in the end
        speech = " and ".join(
            [", ".join(product_names[:-1]), product_names[-1]])
    else:
        # If one or none, then return the list content in a string
        speech = ", ".join(product_names)
    return speech

def get_resolved_value(request, slot_name):
    """Resolve the slot name from the request using resolutions."""
    # type: (IntentRequest, str) -> Union[str, None]
    try:
        return (request.intent.slots[slot_name].resolutions.
                resolutions_per_authority[0].values[0].value.name)
    except (AttributeError, ValueError, KeyError, IndexError):
        return None

def get_spoken_value(request, slot_name):
    """Resolve the slot to the spoken value."""
    # type: (IntentRequest, str) -> Union[str, None]
    try:
        return request.intent.slots[slot_name].value
    except (AttributeError, ValueError, KeyError, IndexError):
        return None

def is_product(product):
    """Is the product list not empty."""
    # type: (List) -> bool
    return bool(product)

def is_entitled(product):
    """Is the product in ENTITLED state."""
    # type: (List) -> bool
    return (is_product(product) and
            product[0].entitled == EntitledState.ENTITLED)

def in_skill_product_response(handler_input):
    """Get the In-skill product response from monetization service."""
    # type: (HandlerInput) -> Union[InSkillProductsResponse, Error]
    locale = handler_input.request_envelope.request.locale
    ms = handler_input.service_client_factory.get_monetization_service()
    return ms.get_in_skill_products(locale)

# Skill Handlers

class LaunchRequestHandler(AbstractRequestHandler):
    """Handler for Launch Requests.
    The handler gets the in-skill products for the user, and provides
    a custom welcome message depending on the ownership of the products
    to the user.
    User says: Alexa, open <skill_name>.
    """
    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return is_request_type("LaunchRequest")(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.info("In LaunchRequestHandler")
        global previous_intent
        previous_intent = None


        in_skill_response = in_skill_product_response(handler_input)
        if isinstance(in_skill_response, InSkillProductsResponse):
            entitled_prods = get_all_entitled_products(in_skill_response.in_skill_products)
            if entitled_prods:
                speech = (
                    "'Welcome to Coin Collector!. You currently own {} products. "
                    "You can add a coin or check what coins you have"
                    "To know what else you can buy, say, 'What can i buy?'. "
                    "So, what can I help you with?").format(get_speakable_list_of_products(entitled_prods))
            else:
                logger.info("No entitled products")
                speech = ('Welcome to Coin Collector!  Lets check up with your collection. '
                        'You can add, check, or delete coins.' )
                reprompt = "What coin do you want to add?"
        else:
            logger.info("Error calling InSkillProducts API: {}".format(
                in_skill_response.message))
            speech = "Something went wrong in loading your purchase history."
            reprompt = speech

        return handler_input.response_builder.speak(speech).ask(
            reprompt).response


class conditionHandler(AbstractRequestHandler):
    """Handler for Launch Requests.
    The handler gets the in-skill products for the user, and provides
    a custom welcome message depending on the ownership of the products
    to the user.
    User says: Alexa, open <skill_name>.
    """
    def can_handle(self, handler_input):
        return is_intent_name("conditionIntent")(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.info("In conditionIntent")
        in_skill_response = in_skill_product_response(handler_input)
        user_id = handler_input.request_envelope.session.user.user_id
        filled_slots = handler_input.request_envelope.request.intent.slots
        slot_values = get_slot_values(filled_slots)
        have_all_access_return = have_all_access(handler_input)
        global previous_intent
        global denomination
        global city
        global year
        global condition
        

        if have_all_access_return == True:
            if previous_intent == "AddCoinIntent":
                previous_intent = "Would you like to add a new coin"
                condition = slot_values["condition"]["resolved"]
                write_to_database(slot_values, user_id, handler_input)
                speech = ("Adding  your "
                    "{} {} {} with condition as {}, Would you like to add a new coin?".format(
                year, city, denomination, condition))
                reprompt = ("Would you like to add a new coin?")
                condition = None
            else:
                condition = slot_values["condition"]["resolved"]
                speech = ("What denomination of coin do you have?")
                reprompt = ("What denomination of coin do you have?")
        else:
            upsell_msg = (
                        "Adding condition to your coins"
                        " is a premium feature. Want to learn more about this?")
            return handler_input.response_builder.add_directive(
                    SendRequestDirective(
                            name="Upsell",
                            payload={
                                "InSkillProduct": {
                                    "productId": "amzn1.adg.product.d1d9f54a-1c1b-449d-a0b6-f89f4617aa6f",
                                },
                                "upsellMessage": upsell_msg,
                            },
                            token="correlationToken")
                    ).response
            
        return handler_input.response_builder.speak(speech).ask(
            reprompt).response


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
        global previous_intent
        logger.info("In CompletedAddCoinIntent")
        filled_slots = handler_input.request_envelope.request.intent.slots
        user_id = handler_input.request_envelope.session.user.user_id
        slot_values = get_slot_values(filled_slots)
        have_all_access_return = have_all_access(handler_input)
        global denomination
        global city
        global year
        global condition
        

        if have_all_access_return == True:
            if condition == None:
                year = slot_values["year"]["resolved"]
                city = slot_values["city"]["resolved"]
                denomination = slot_values["coin"]["resolved"]
                previous_intent = "AddCoinIntent"
                speech = ("What is the condition of the coin?")
                reprompt = ("What is the condition of the coin?")
            else:
                previous_intent = "Would you like to add a new coin"
                year = slot_values["year"]["resolved"]
                city = slot_values["city"]["resolved"]
                denomination = slot_values["coin"]["resolved"]
                write_to_database(slot_values, user_id, handler_input)
                speech = ("Adding  your "
                    "{} {} {} with condition as {},  Would you like to add another coin?".format(
                year, city, denomination, condition))
                reprompt = ("Would you like to add a new coin?")
        else:
            previous_intent = "Would you like to add a new coin"
            write_to_database(slot_values, user_id, handler_input)
            speech = ("Adding  your "
                    "{} "
                    "{} "
                    "{}, Would you like to add another coin?".format(
            slot_values["year"]["resolved"],
            slot_values["city"]["resolved"],
            slot_values["coin"]["resolved"]))

            reprompt = ("Would you like to add a new coin")
        return handler_input.response_builder.speak(speech).ask(
            reprompt).response



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

        print("helpppppppppppppp")
    
        speech = ("Deleting now, What would you like to do next?")
        reprompt = ("What would you like to do next?")

        return handler_input.response_builder.speak(speech).ask(reprompt).response


class YesHandler(AbstractRequestHandler):
    """If the user says Yes, they want another fact."""
    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return is_intent_name("AMAZON.YesIntent")(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.info("In YesHandler")
        global previous_intent
        if previous_intent == "Delete":
            speech = ("Deleting now, What would you like to do next?")
            reprompt = ("What would you like to do next?")
            previous_intent = "Leave"
        if previous_intent == "Would you like to add a new coin":
            speech = ("What denomination of coin do you have?")
            reprompt = ("What denomination of coin do you have?")
        else:
            speech= ("Sorry, I can't understand the command. Say help to recieve help. What would you like to do next?")
            reprompt = ("What would you like to do next?")
        return handler_input.response_builder.speak(speech).ask(reprompt).response



class NoHandler(AbstractRequestHandler):
    """If the user says No, then the skill should be exited."""
    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return is_intent_name("AMAZON.NoIntent")(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        global previous_intent
        if previous_intent == "Delete":
            speech = ("What would you like to do next?")
            reprompt = ("What would you like to do next?")
        if previous_intent == "Leave":
            return handler_input.response_builder.speak(
            get_random_goodbye()).set_should_end_session(True).response
        if previous_intent == "Would you like to add a new coin":
            speech = ("What would you like to do next?")
            reprompt = ("What would you like to do next?")
            previous_intent = "Leave"
        
        else:
            speech= ("Sorry, I can't understand the command. Say help to recieve help. What would you like to do next?")
            reprompt = ("What would you like to do next?")
        return handler_input.response_builder.speak(speech).ask(reprompt).response


class ShoppingHandler(AbstractRequestHandler):
    """
    Following handler demonstrates how skills can handle user requests to
    discover what products are available for purchase in-skill.
    User says: Alexa, ask Premium facts what can I buy.
    """
    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return is_intent_name("ShoppingIntent")(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.info("In ShoppingHandler")

        # Inform the user about what products are available for purchase
        in_skill_response = in_skill_product_response(handler_input)
        if in_skill_response:
            purchasable = [l for l in in_skill_response.in_skill_products
                           if l.entitled == EntitledState.NOT_ENTITLED and
                           l.purchasable == PurchasableState.PURCHASABLE]

            if purchasable:
                speech = ("Products available for purchase at this time are {}.  "
                          "To learn more about all access say, 'Tell me more "
                          "about all access' If you are ready "
                          "to buy say 'Buy all access' So what "
                          "can I help you with?").format(
                    get_speakable_list_of_products(purchasable))
            else:
                speech = ("There are no more products to buy. To add a coin "
                          "you could say, 'add a coin', or "
                          "you can check what coins you have "
                          "for example, say 'How many pennies do I have"
                          " So what can I help you with?")
            reprompt = "I didn't catch that. What can I help you with?"
            return handler_input.response_builder.speak(speech).ask(
                reprompt).response


class ProductDetailHandler(AbstractRequestHandler):
    """Handler for providing product detail to the user before buying.
    Resolve the product category and provide the user with the
    corresponding product detail message.
    User says: Alexa, tell me about <category> pack
    """
    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return is_intent_name("ProductDetailIntent")(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.info("In ProductDetailHandler")
        in_skill_response = in_skill_product_response(handler_input)

        if in_skill_response:
            # No entity resolution match
            product_category = "all_access"

            product = [l for l in in_skill_response.in_skill_products
                        if l.reference_name == product_category]
            if is_product(product):
                speech = ("{}.  To buy it, say Buy {}".format(
                    product[0].summary, product[0].name))
                reprompt = (
                    "I didn't catch that. To buy {}, say Buy {}".format(
                        product[0].name, product[0].name))
            else:
                speech = ("I don't think we have a product by that name.  "
                            "Can you try again?")
                reprompt = "I didn't catch that. Can you try again?"

            return handler_input.response_builder.speak(speech).ask(
                    reprompt).response

class BuyHandler(AbstractRequestHandler):
    """Handler for lett users buy the product.
    User says: Alexa, buy <category>.
    """
    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return is_intent_name("BuyIntent")(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.info("In BuyHandler")

        # Inform the user about what products are available for purchase
        in_skill_response = in_skill_product_response(handler_input)
        if in_skill_response:
            product_category = "all_access"

            product = [l for l in in_skill_response.in_skill_products
                       if l.reference_name == product_category]
            return handler_input.response_builder.add_directive(
                SendRequestDirective(
                    name="Buy",
                    payload={
                        "InSkillProduct": {
                            "productId": product[0].product_id
                        }
                    },
                    token="correlationToken")
            ).response

class CancelSubscriptionHandler(AbstractRequestHandler):
    """
    Following handler demonstrates how Skills would receive Cancel requests
    from customers and then trigger a cancel request to Alexa
    User says: Alexa, ask premium facts to cancel <product name>
    """
    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return is_intent_name("CancelSubscriptionIntent")(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.info("In CancelSubscriptionHandler")

        in_skill_response = in_skill_product_response(handler_input)
        if in_skill_response:
            

            product_category = "all_access"

            product = [l for l in in_skill_response.in_skill_products
                        if l.reference_name == product_category]
            return handler_input.response_builder.add_directive(
                SendRequestDirective(
                    name="Cancel",
                    payload={
                        "InSkillProduct": {
                            "productId": product[0].product_id
                        }
                    },
                    token="correlationToken")
            ).response

class BuyResponseHandler(AbstractRequestHandler):
    """This handles the Connections.Response event after a buy occurs."""
    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return (is_request_type("Connections.Response")(handler_input) and
                handler_input.request_envelope.request.name == "Buy")

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.info("In BuyResponseHandler")
        in_skill_response = in_skill_product_response(handler_input)
        product_id = "amzn1.adg.product.d1d9f54a-1c1b-449d-a0b6-f89f4617aa6f"

        if in_skill_response:
            product = [l for l in in_skill_response.in_skill_products
                       if l.product_id == product_id]
            logger.info("Product = {}".format(str(product)))
            if handler_input.request_envelope.request.status.code == "200":
                speech = None
                reprompt = None
                purchase_result = handler_input.request_envelope.request.payload.get(
                    "purchaseResult")
                if purchase_result == PurchaseResult.ACCEPTED.value:
                    if product[0].reference_name != "all_access":
                        speech = ("You have just bought all access which allows you to add condition to your coin description. "
                                "Try it now, say 'Add a 2019 D Penny with grading 60'")
                        reprompt = get_random_yes_no_question()
                elif purchase_result in (
                        PurchaseResult.DECLINED.value,
                        PurchaseResult.ERROR.value,
                        PurchaseResult.NOT_ENTITLED.value):
                    speech = ("Thanks for your interest in all access.  "
                              "Would you like to add another coin?")

                    reprompt = "Would you like to add another coin?"
                elif purchase_result == PurchaseResult.ALREADY_PURCHASED.value:
                    logger.info("Already purchased product")
                    speech = "Would you like to add another coin?"
                    reprompt = "What can I help you with?"
                else:
                    # Invalid purchase result value
                    logger.info("Purchase result: {}".format(purchase_result))
                    return FallbackIntentHandler().handle(handler_input)

                return handler_input.response_builder.speak(speech).ask(
                    reprompt).response
            else:
                logger.log("Connections.Response indicated failure. "
                           "Error: {}".format(
                    handler_input.request_envelope.request.status.message))

                return handler_input.response_builder.speak(
                    "There was an error handling your purchase request. "
                    "Please try again or contact us for help").response

class CancelResponseHandler(AbstractRequestHandler):
    """This handles the Connections.Response event after a cancel occurs."""
    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return (is_request_type("Connections.Response")(handler_input) and
                handler_input.request_envelope.request.name == "Cancel")

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.info("In CancelResponseHandler")
        in_skill_response = in_skill_product_response(handler_input)
        product_id = "amzn1.adg.product.d1d9f54a-1c1b-449d-a0b6-f89f4617aa6f"

        if in_skill_response:
            product = [l for l in in_skill_response.in_skill_products
                       if l.product_id == product_id]
            logger.info("Product = {}".format(str(product)))
            if handler_input.request_envelope.request.status.code == "200":
                speech = None
                reprompt = None
                purchase_result = handler_input.request_envelope.request.payload.get(
                        "purchaseResult")
                purchasable = product[0].purchasable
                if purchase_result == PurchaseResult.ACCEPTED.value:
                    speech = ("You have successfully cancelled your "
                              "subscription. What would you like to do next?")
                    reprompt = ("What would you like to do next?")

                if purchase_result == PurchaseResult.DECLINED.value:
                    if purchasable == PurchasableState.PURCHASABLE:
                        speech = ("You don't currently have a "
                              "subscription. What would you like to do next?")
                    else:
                        speech = ("What would you like to do next?")
                        reprompt = ("What would you like to do next?")

                return handler_input.response_builder.speak(speech).ask(
                    reprompt).response
            else:
                logger.log("Connections.Response indicated failure. "
                           "Error: {}".format(
                    handler_input.request_envelope.request.status.message))

                return handler_input.response_builder.speak(
                        "There was an error handling your cancellation "
                        "request. Please try again or contact us for "
                        "help").response

class UpsellResponseHandler(AbstractRequestHandler):
    """This handles the Connections.Response event after an upsell occurs."""
    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return (is_request_type("Connections.Response")(handler_input) and
                handler_input.request_envelope.request.name == "Upsell")

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.info("In UpsellResponseHandler")

        if handler_input.request_envelope.request.status.code == "200":
            if handler_input.request_envelope.request.payload.get(
                    "purchaseResult") == PurchaseResult.DECLINED.value:
                speech = ("Ok. What coin would you like to add?")
                reprompt = get_random_yes_no_question()
                return handler_input.response_builder.speak(speech).ask(
                    reprompt).response
        else:
            logger.log("Connections.Response indicated failure. "
                       "Error: {}".format(
                handler_input.request_envelope.request.status.message))
            return handler_input.response_builder.speak(
                "There was an error handling your Upsell request. "
                "Please try again or contact us for help.").response

class HelpIntentHandler(AbstractRequestHandler):
    """Handler for help message to users."""
    def can_handle(self, handler_input):
        return is_intent_name("AMAZON.HelpIntent")(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.info("In HelpIntentHandler")
        in_skill_response = in_skill_product_response(handler_input)

        if isinstance(in_skill_response, InSkillProductsResponse):
            speech = (
                "To add a coin you can say 'Add a 2019 penny,' you can check what coins you have by asking 'How many pennies do I have?' "
                "You can delete your coins by saying 'Delete my 2019 D Penny,' "
                " or to hear about all access "
                " say 'What is all access'. "
                "So, what can I help you with?"
            )
            reprompt = "I didn't catch that. What can I help you with?"
        else:
            logger.info("Error calling InSkillProducts API: {}".format(
                in_skill_response.message))
            speech = "Something went wrong in loading your purchase history."
            reprompt = speech

        return handler_input.response_builder.speak(speech).ask(
            reprompt).response


class FallbackIntentHandler(AbstractRequestHandler):
    """Handler for fallback intent.
    2018-July-12: AMAZON.FallbackIntent is currently available in all
    English locales. This handler will not be triggered except in that
    locale, so it can be safely deployed for any locale. More info
    on the fallback intent can be found here: https://developer.amazon.com/docs/custom-skills/standard-built-in-intents.html#fallback
    """
    def can_handle(self, handler_input):
        return is_intent_name("AMAZON.FallbackIntent")(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.info("In FallbackIntentHandler")
        speech = (
                "Sorry. I cannot help with that. I can help you with "
                "To add a coin you can say 'Add a 2019 penny,' you can check what coins you have by asking 'How many pennies do I have?' "
                "You can delete your coins by saying 'Delete my 2019 D Penny,' "
                " or to hear about all access "
                " say 'What is all access'. "
                "So, what can I help you with?"
            )
        reprompt = "I didn't catch that. What can I help you with?"

        return handler_input.response_builder.speak(speech).ask(
            reprompt).response


class SessionEndedHandler(AbstractRequestHandler):
    """Handler for session end request, stop or cancel intents."""
    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return (is_request_type("SessionEndedRequest")(handler_input) or
                is_intent_name("AMAZON.StopIntent")(handler_input) or
                is_intent_name("AMAZON.CancelIntent")(handler_input))

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.info("In SessionEndedHandler")
        return handler_input.response_builder.speak(
            get_random_goodbye()).set_should_end_session(True).response

# Skill Exception Handler
class CatchAllExceptionHandler(AbstractExceptionHandler):
    """One exception handler to catch all exceptions."""
    def can_handle(self, handler_input, exception):
        # type: (HandlerInput, Exception) -> bool
        return True

    def handle(self, handler_input, exception):
        # type: (HandlerInput, Exception) -> Response
        logger.error(exception, exc_info=True)

        speech = "Sorry, I can't understand the command. Please try again!!"
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

def write_to_database(slot_values, user_id, handler_input):
    global denomination
    global city
    global year
    global condition
    have_all_access_return = have_all_access(handler_input)

    if have_all_access_return == True:
        new_coin = {"year": year,
                    "city": city,
                    "coin": denomination,
                    "condition":condition}
    else:
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
    grade = slot_values["condition"]["resolved"]



    get_search_coin_criteria = {"year": year, "city":city, "coin":coin, "condition": grade}

    return get_search_coin_criteria    

def check_for_coin(slot_values,user_id):

    right_coins= []
    have_coin = False


    for coin in coin_collection_list(user_id):
        if coin.get("year") == get_search_coin_criteria(slot_values).get("year") or get_search_coin_criteria(slot_values).get("year") == None:
            if coin.get("city") == get_search_coin_criteria(slot_values).get("city") or get_search_coin_criteria(slot_values).get("city") == None:
                if coin.get("coin") == get_search_coin_criteria(slot_values).get("coin") or get_search_coin_criteria(slot_values).get("coin") == None:
                    if coin.get("condition") == get_search_coin_criteria(slot_values).get("condition") or get_search_coin_criteria(slot_values).get("condition") == None:
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

def have_all_access(handler_input):
    in_skill_response = in_skill_product_response(handler_input)
    have_all_access = False
    if in_skill_response:
        subscription = [
            l for l in in_skill_response.in_skill_products
            if l.reference_name == "all_access"]
    if is_entitled(subscription):
        have_all_access = True

    return have_all_access          




sb = StandardSkillBuilder()

sb.add_request_handler(LaunchRequestHandler())
sb.add_request_handler(InProgressAddCoinIntent())
sb.add_request_handler(CompletedAddCoinIntent())
sb.add_request_handler(InProgressReadCoinIntent())
sb.add_request_handler(CompletedReadCoinIntent())
sb.add_request_handler(InProgressDeleteCoinIntent())
sb.add_request_handler(CompletedDeleteCoinIntent())
sb.add_request_handler(YesHandler())
sb.add_request_handler(NoHandler())
sb.add_request_handler(BuyResponseHandler())
sb.add_request_handler(CancelResponseHandler())
sb.add_request_handler(UpsellResponseHandler())
sb.add_request_handler(ShoppingHandler())
sb.add_request_handler(ProductDetailHandler())
sb.add_request_handler(BuyHandler())
sb.add_request_handler(conditionHandler())
sb.add_request_handler(CancelSubscriptionHandler())
sb.add_request_handler(HelpIntentHandler())
sb.add_request_handler(FallbackIntentHandler())
sb.add_request_handler(SessionEndedHandler())

sb.add_exception_handler(CatchAllExceptionHandler())
sb.add_global_request_interceptor(RequestLogger())
sb.add_global_response_interceptor(ResponseLogger())

lambda_handler = sb.lambda_handler()