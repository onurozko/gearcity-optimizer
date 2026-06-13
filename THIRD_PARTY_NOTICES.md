# Third-Party Notices

## GearCity

This project is an unofficial fan-made helper for GearCity.

GearCity is developed and published by Visual Entertainment And Technologies.

This project is not affiliated with or endorsed by GearCity or Visual
Entertainment And Technologies.

## GearCity Wiki

This project can download and parse selected GearCity Wiki pages listed in
`sources/wiki_urls.json`.

The wiki content is used as reference material for vehicle type priorities and
game-mechanics pseudo-code.

GearCity Wiki content is licensed under
[CC Attribution-NonCommercial-ShareAlike 4.0 International](https://creativecommons.org/licenses/by-nc-sa/4.0/)
unless otherwise noted on the wiki.

Configured wiki pages:

- [Vehicle Type Importance](https://wiki.gearcity.info/doku.php?id=gamemanual:references_vehicletypeimportance)
- [Chassis Game Mechanics](https://wiki.gearcity.info/doku.php?id=gamemanual:gm_chassis_design)
- [Engine Game Mechanics](https://wiki.gearcity.info/doku.php?id=gamemanual:gm_engines_design)
- [Gearbox Game Mechanics](https://wiki.gearcity.info/doku.php?id=gamemanual:gm_gearboxes_design)
- [Dynamic Reports](https://wiki.gearcity.info/doku.php?id=gamemanual:gui_dynamicreports)

## Local generated files

Files under `generated/` are parser outputs or generated calculator outputs and
should generally not be committed.

Files under `sources/wiki_html/`, `sources/wiki_raw/`, and `sources/wiki_text/`
are cached wiki downloads and should not be committed.

Files under `sources/game_files/` are local GearCity installation references and
must not be committed.
