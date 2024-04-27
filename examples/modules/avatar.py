import discohook


@discohook.command.user(permissions=[discohook.Permission.send_messages])
async def avatar(inter: discohook.Interaction, user: discohook.User):
    embed = discohook.Embed(title=f"{user.global_name}")
    embed.set_image(user.avatar.url)
    await inter.response.send(embed=embed)


# don't forget to add setup function
def setup(client: discohook.Client):
    client.add_commands(avatar)
