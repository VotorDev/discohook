import asyncio

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey

from .command import ApplicationCommand, ApplicationCommandOptionType
from .enums import (
    ApplicationCommandType,
    InteractionCallbackType,
    InteractionType,
    MessageComponentType,
)
from .errors import GlobalException
from .interaction import Interaction
from .resolver import (
    build_context_menu_param,
    build_modal_params,
    build_select_menu_values,
    build_slash_command_prams,
)


# noinspection PyProtectedMember
async def handler(request: Request):
    """
    Handles all interactions from discord

    Note: This is not a public API and should not be used outside the library
    """
    signature = request.headers.get("X-Signature-Ed25519")
    timestamp = request.headers.get("X-Signature-Timestamp")
    try:
        key = VerifyKey(bytes.fromhex(request.app.public_key))
        key.verify(str(timestamp).encode() + await request.body(), bytes.fromhex(str(signature)))
    except BadSignatureError:
        return Response(content="BadSignature", status_code=401)

    data = await request.json()
    interaction = Interaction(request.app, data)
    try:
        if interaction.type == InteractionType.ping:
            return JSONResponse({"type": InteractionCallbackType.pong.value}, status_code=200)

        elif interaction.type == InteractionType.app_command:
            key = f"{interaction.data['name']}:{interaction.data['type']}"
            cmd: ApplicationCommand = request.app.application_commands.get(key)
            if not cmd:
                raise Exception(f"command `{interaction.data['name']}` ({interaction.data['id']}) not found")

            if cmd.checks:
                results = await asyncio.gather(*[check(interaction) for check in cmd.checks])
                for result in results:
                    if not isinstance(result, bool):
                        raise TypeError(f"check returned {type(result)}, expected bool")
                if not all(results):
                    raise Exception(f"command checks failed")

            if not (interaction.data["type"] == ApplicationCommandType.slash.value):
                target_object = build_context_menu_param(interaction)
                await cmd(interaction, target_object)

            elif interaction.data.get("options") and (
                interaction.data["options"][0]["type"] == ApplicationCommandOptionType.subcommand.value
            ):
                subcommand = cmd.subcommands[interaction.data["options"][0]["name"]]
                args, kwargs = build_slash_command_prams(subcommand.callback, interaction)
                await subcommand(interaction, *args, **kwargs)
            else:
                args, kwargs = build_slash_command_prams(cmd.callback, interaction)
                await cmd(interaction, *args, **kwargs)

        elif interaction.type == InteractionType.autocomplete:
            key = f"{interaction.data['name']}:{interaction.data['type']}"
            cmd: ApplicationCommand = request.app.application_commands.get(key)
            if not cmd:
                raise Exception(f"command `{interaction.data['name']}` ({interaction.data['id']}) not found")
            if interaction.data["options"][0]["type"] == ApplicationCommandOptionType.subcommand.value:
                subcommand_name = interaction.data["options"][0]["name"]
                option = interaction.data["options"][0]["options"][0]
                callback = cmd.subcommands[subcommand_name].autocompletes.get(option["name"])
            else:
                option = interaction.data["options"][0]
                callback = cmd.autocompletes.get(option["name"])
            if callback:
                await callback(interaction, option["value"])

        elif interaction.type in (InteractionType.component, InteractionType.modal_submit):
            custom_id = interaction.data["custom_id"]
            if request.app._custom_id_parser:
                custom_id = await request.app._custom_id_parser(custom_id)
            component = request.app.active_components.get(custom_id)
            if not component:
                raise Exception(f"component `{custom_id}` not found")
            if component.checks:
                results = await asyncio.gather(*[check(interaction) for check in component.checks])
                for result in results:
                    if not isinstance(result, bool):
                        raise TypeError(f"check returned {type(result)}, expected bool")
                if not all(results):
                    raise Exception("component checks failed")

            if interaction.type == InteractionType.component:
                if interaction.data["component_type"] == MessageComponentType.button.value:
                    await component(interaction)
                if interaction.data["component_type"] in (
                    MessageComponentType.text_select.value,
                    MessageComponentType.user_select.value,
                    MessageComponentType.role_select.value,
                    MessageComponentType.channel_select.value,
                    MessageComponentType.mentionable_select.value
                ):
                    await component(interaction, build_select_menu_values(interaction))

            elif interaction.type == InteractionType.modal_submit:
                args, kwargs = build_modal_params(component.callback, interaction)
                await component(interaction, *args, **kwargs)
        else:
            raise Exception(f"unhandled interaction type", interaction)
    except Exception as e:
        raise GlobalException(str(e), interaction)
    else:
        return Response(status_code=200)
