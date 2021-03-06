#!/usr/bin/env python
#
# Electrum-NMC - lightweight Namecoin client
# Copyright (C) 2018 Namecoin Developers
#
# Permission is hereby granted, free of charge, to any person
# obtaining a copy of this software and associated documentation files
# (the "Software"), to deal in the Software without restriction,
# including without limitation the rights to use, copy, modify, merge,
# publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS
# BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN
# ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

def split_name_script(decoded):
    # This case happens if a script was malformed and couldn't be decoded by
    # transaction.get_address_from_output_script.
    if decoded is None:
        return {"name_op": None, "address_scriptPubKey": decoded}

    # name_new TxOuts look like:
    # NAME_NEW (hash) 2DROP (Bitcoin TxOut)
    match = [ OP_NAME_NEW, OPPushDataGeneric, opcodes.OP_2DROP ]
    if match_decoded(decoded[:len(match)], match):
        return {"name_op": {"op": OP_NAME_NEW, "hash": decoded[1][1]}, "address_scriptPubKey": decoded[len(match):]}

    # name_firstupdate TxOuts look like:
    # NAME_FIRSTUPDATE (name) (rand) (value) 2DROP 2DROP (Bitcoin TxOut)
    match = [ OP_NAME_FIRSTUPDATE, OPPushDataGeneric, OPPushDataGeneric, OPPushDataGeneric, opcodes.OP_2DROP, opcodes.OP_2DROP ]
    if match_decoded(decoded[:len(match)], match):
        return {"name_op": {"op": OP_NAME_FIRSTUPDATE, "name": decoded[1][1], "rand": decoded[2][1], "value": decoded[3][1]}, "address_scriptPubKey": decoded[len(match):]}

    # name_update TxOuts look like:
    # NAME_UPDATE (name) (value) 2DROP DROP (Bitcoin TxOut)
    match = [ OP_NAME_UPDATE, OPPushDataGeneric, OPPushDataGeneric, opcodes.OP_2DROP, opcodes.OP_DROP ]
    if match_decoded(decoded[:len(match)], match):
        return {"name_op": {"op": OP_NAME_UPDATE, "name": decoded[1][1], "value": decoded[2][1]}, "address_scriptPubKey": decoded[len(match):]}

    return {"name_op": None, "address_scriptPubKey": decoded}

def get_name_op_from_output_script(_bytes):
    try:
        decoded = [x for x in script_GetOp(_bytes)]
    except MalformedBitcoinScript:
        decoded = None

    # Extract the name script if one is present.
    return split_name_script(decoded)["name_op"]

def name_op_to_script(name_op):
    if name_op is None:
        script = ''
    elif name_op["op"] == OP_NAME_NEW:
        script = '51'                                 # OP_NAME_NEW
        script += push_script(bh2u(name_op["hash"]))
        script += '6d'                                # OP_2DROP
    elif name_op["op"] == OP_NAME_FIRSTUPDATE:
        script = '52'                                 # OP_NAME_FIRSTUPDATE
        script += push_script(bh2u(name_op["name"]))
        script += push_script(bh2u(name_op["rand"]))
        script += push_script(bh2u(name_op["value"]))
        script += '6d'                                # OP_2DROP
        script += '6d'                                # OP_2DROP
    elif name_op["op"] == OP_NAME_UPDATE:
        script = '53'                                 # OP_NAME_UPDATE
        script += push_script(bh2u(name_op["name"]))
        script += push_script(bh2u(name_op["value"]))
        script += '6d'                                # OP_2DROP
        script += '75'                                # OP_DROP
    else:
        raise BitcoinException('unknown name op: {}'.format(name_op))
    return script

def build_name_new(identifier, rand = None):
    if rand is None:
        rand = os.urandom(20)

    to_hash = rand + identifier
    commitment = hash_160(to_hash)

    return {"op": OP_NAME_NEW, "hash": commitment}, rand

def name_identifier_to_scripthash(identifier_bytes):
    name_op = {"op": OP_NAME_UPDATE, "name": identifier_bytes, "value": bytes([])}
    script = name_op_to_script(name_op)
    script += '6a' # OP_RETURN

    return script_to_scripthash(script)


def format_name_identifier(identifier_bytes):
    try:
        identifier = identifier_bytes.decode("ascii")
    except UnicodeDecodeError:
        return format_name_identifier_unknown_hex(identifier_bytes)

    is_domain_namespace = identifier.startswith("d/")
    if is_domain_namespace:
        return format_name_identifier_domain(identifier)

    is_identity_namespace = identifier.startswith("id/")
    if is_identity_namespace:
        return format_name_identifier_identity(identifier)

    return format_name_identifier_unknown(identifier)


def format_name_identifier_domain(identifier):
    label = identifier[len("d/"):]

    if len(label) < 1:
        return format_name_identifier_unknown(identifier)

    # Source: https://github.com/namecoin/proposals/blob/master/ifa-0001.md#keys
    if len(label) > 63:
        return format_name_identifier_unknown(identifier)

    # Source: https://github.com/namecoin/proposals/blob/master/ifa-0001.md#keys
    label_regex = r"^(xn--)?[a-z0-9]+(-[a-z0-9]+)*$"
    label_match = re.match(label_regex, label)
    if label_match is None:
        return format_name_identifier_unknown(identifier)

    # Reject digits-only labels
    number_regex = r"^[0-9]+$"
    number_match = re.match(number_regex, label)
    if number_match is not None:
        return format_name_identifier_unknown(identifier)

    return "Domain " + label + ".bit"


def format_name_identifier_identity(identifier):
    label = identifier[len("id/"):]

    if len(label) < 1:
        return format_name_identifier_unknown(identifier)

    # Max id/ identifier length is 255 chars according to wiki spec.  But we
    # don't need to check for this, because that's also the max length of an
    # identifier under the Namecoin consensus rules.

    # Same as d/ regex but without IDN prefix.
    # TODO: this doesn't exactly match the https://wiki.namecoin.org spec.
    label_regex = r"^[a-z0-9]+(-[a-z0-9]+)*$"
    label_match = re.match(label_regex, label)
    if label_match is None:
        return format_name_identifier_unknown(identifier)

    return "Identity " + label

def format_name_identifier_unknown(identifier):
    # Check for non-printable characters, and print ASCII if none are found.
    if identifier.isprintable():
        return 'Non-standard name "' + identifier + '"'

    return format_name_identifier_unknown_hex(identifier.encode("ascii"))


def format_name_identifier_unknown_hex(identifier_bytes):
    return "Non-standard hex name " + bh2u(identifier_bytes)


def format_name_value(identifier_bytes):
    try:
        identifier = identifier_bytes.decode("ascii")
    except UnicodeDecodeError:
        return format_name_value_hex(identifier_bytes)

    if not identifier.isprintable():
        return format_name_value_hex(identifier_bytes)

    return "ASCII " + identifier


def format_name_value_hex(identifier_bytes):
    return "Hex " + bh2u(identifier_bytes)


def format_name_op(name_op):
    if name_op is None:
        return ''
    if "hash" in name_op:
        formatted_hash = "Commitment = " + bh2u(name_op["hash"])
    if "rand" in name_op:
        formatted_rand = "Salt = " + bh2u(name_op["rand"])
    if "name" in name_op:
        formatted_name = "Name = " + format_name_identifier(name_op["name"])
    if "value" in name_op:
        formatted_value = "Data = " + format_name_value(name_op["value"])

    if name_op["op"] == OP_NAME_NEW:
        return "\tPre-Registration\n\t\t" + formatted_hash
    if name_op["op"] == OP_NAME_FIRSTUPDATE:
        return "\tRegistration\n\t\t" + formatted_name + "\n\t\t" + formatted_rand + "\n\t\t" + formatted_value
    if name_op["op"] == OP_NAME_UPDATE:
        return "\tUpdate\n\t\t" + formatted_name + "\n\t\t" + formatted_value


def get_default_name_tx_label(wallet, tx):
    for o in tx.outputs():
        name_op = o.name_op
        if name_op is not None:
            # TODO: Handle multiple atomic name ops.
            name_input_is_mine, name_output_is_mine = get_wallet_name_delta(wallet, tx)
            if not name_input_is_mine and not name_output_is_mine:
                return None
            if name_input_is_mine and not name_output_is_mine:
                return "Transfer (Outgoing): " + format_name_identifier(name_op["name"])
            if not name_input_is_mine and name_output_is_mine:
                # A name_new transaction isn't expected to have a name input,
                # so we don't consider it a transfer.
                if name_op["op"] != OP_NAME_NEW:
                    return "Transfer (Incoming): " + format_name_identifier(name_op["name"])
            if name_op["op"] == OP_NAME_NEW:
                # A name_new transaction doesn't have a name output, so there's
                # nothing to format.
                return "Pre-Registration"
            if name_op["op"] == OP_NAME_FIRSTUPDATE:
                return "Registration: " + format_name_identifier(name_op["name"])
            if name_op["op"] == OP_NAME_UPDATE:
                return "Update: " + format_name_identifier(name_op["name"])
    return None


def get_wallet_name_delta(wallet, tx):
    name_input_is_mine = False
    name_output_is_mine = False
    for txin in tx.inputs():
        addr = wallet.get_txin_address(txin)
        if wallet.is_mine(addr):
            prev_tx = wallet.transactions.get(txin['prevout_hash'])
            if prev_tx.outputs()[txin['prevout_n']].name_op is not None:
                name_input_is_mine = True
    for o in tx.outputs():
        if o.name_op is not None and wallet.is_mine(o.address):
            name_output_is_mine = True

    return name_input_is_mine, name_output_is_mine


def name_expires_in(name_height, chain_height):
    if name_height <= 0:
        return None

    return name_height - chain_height + 36000


import binascii
import os
import re

from .bitcoin import push_script, script_to_scripthash
from .crypto import hash_160
from .transaction import MalformedBitcoinScript, match_decoded, opcodes, OPPushDataGeneric, script_GetOp
from .util import bh2u

OP_NAME_NEW = opcodes.OP_1
OP_NAME_FIRSTUPDATE = opcodes.OP_2
OP_NAME_UPDATE = opcodes.OP_3

