# Анатомические 3D-модели

Модели органов в этой папке (`*.npz` — геометрия, `*.json` — группы, цвета и источник в поле
`attribution`) получены из трёх открытых источников. В окне 3D-просмотра под каждой моделью
выводится подпись её источника.

| Источник | Органы | Лицензия |
|---|---|---|
| BodyParts3D | сердце, мозг, печень, жёлчный пузырь, желудок, кишечник, почки, поджелудочная железа, мочевой пузырь, надпочечники, пищевод, прямая кишка, аппендикс, трахея | CC BY 4.0 |
| Human Reference Atlas (HuBMAP) | лёгкие, селезёнка, простата, матка, яичники | CC BY 4.0 |
| Атлас головы и шеи SPL / Open Anatomy | щитовидная железа | 3D Slicer License, часть B |

## BodyParts3D

**BodyParts3D, © The Database Center for Life Science licensed under CC Attribution 4.0 International**

- база: https://dbarchive.biosciencedbc.jp/en/bodyparts3d/
- лицензия: https://dbarchive.biosciencedbc.jp/en/bodyparts3d/lic.html (CC BY 4.0)
- исходные файлы: `partof_BP3D_4.0_obj_99.zip` и `partof_element_parts.txt` (PART-OF tree, версия 4.0)

В заголовках исходных OBJ-файлов осталась прежняя лицензия CC BY-SA 2.1 Japan; действующей
считается лицензия на странице базы (CC BY 4.0).

Что изменено относительно оригинала (скрипт `tools/bp3d_import.py`, его можно запустить заново):

- сетки упрощены (кластеризация вершин) и сглажены (фильтр Таубина), грубые сетки подразделены;
- переведены из миллиметров в единицы сцены и отцентрованы;
- убраны части, невидимые снаружи (клапаны, желудочки мозга, внутренние сосуды и протоки);
- коронарные сосуды сердца выдвинуты на 1 мм наружу, сегменты печени раздуты на 1,2 мм,
  чтобы закрыть щели между ними;
- части окрашены по названиям и объединены в группы материалов;
- жёлчный пузырь вынесен из модели печени в отдельную модель `gallbladder` (та же геометрия,
  те же координаты; при новом импорте он собирается отдельно);
- для ориентира к некоторым органам добавлены соседние: к надпочечникам — почки,
  к пищеводу — желудок, к аппендиксу — слепая кишка, к трахее — главные бронхи.

Щитовидной железы, селезёнки, матки и яичников в BodyParts3D 4.0 нет. Поверхности лёгких
там тоже нет (только бронхиальное дерево и сосуды), поэтому лёгкие взяты из Human Reference Atlas.

## Human Reference Atlas (HuBMAP)

**3D Reference Organs of the Human Reference Atlas, Human BioMolecular Atlas Program (HuBMAP),
based on the Visible Human Project of the U.S. National Library of Medicine;
licensed under CC Attribution 4.0 International**

- библиотека: https://humanatlas.io/3d-reference-library
- лицензия: https://creativecommons.org/licenses/by/4.0/
- исходные файлы (`https://cdn.humanatlas.io/digital-objects/ref-organ/<орган>/<версия>/assets/<файл>`):
  `lung-male/v1.4/3d-vh-m-lung.glb`, `trachea-male/v1.1/3d-vh-m-trachea.glb`,
  `spleen-male/v1.3/3d-vh-m-spleen.glb`, `prostate-male/v1.2/3d-vh-m-prostate.glb`,
  `uterus-female/v1.2/3d-vh-f-uterus.glb`, `ovary-female-left/v1.3/3d-vh-f-ovary-l.glb`,
  `ovary-female-right/v1.3/3d-vh-f-ovary-r.glb`, `fallopian-tube-female-left/v1.2/3d-vh-f-fallopian-tube-l.glb`,
  `fallopian-tube-female-right/v1.2/3d-vh-f-fallopian-tube-r.glb`

Что изменено (скрипт `tools/atlas_import.py`):

- переведены из метров и осей glTF в миллиметры и оси проекта, затем — в единицы сцены;
- лоскуты одной поверхности (стороны селезёнки, бронхолёгочные сегменты лёгких, части матки
  и маточных труб) сварены по общим вершинам в одну сетку;
- упрощены, сглажены и очищены от невидимых снаружи частей так же, как модели BodyParts3D;
- матка и яичники собраны в одну сцену с маточными трубами (у модели яичников матка и трубы приглушены);
- части окрашены и объединены в группы материалов.

## Атлас головы и шеи SPL / Open Anatomy

**CT-based Atlas of the Head and Neck (2016-09), Surgical Planning Laboratory,
Brigham and Women's Hospital; Open Anatomy Project**

- атлас: https://www.openanatomy.org/atlases/nac/head-neck-2016-09/
- описание: https://nac.spl.harvard.edu/publications/ct-based-atlas-head-and-neck
- исходные файлы: `models/Model_118_thyroid_gland.vtk`, `models/Model_120_cricoid_cartilage.vtk`
- лицензия: 3D Slicer License, часть B — полный текст в `LICENSE-3D-Slicer.txt` рядом с этим файлом.
  Модель изменена (см. ниже) и не является оригинальными данными атласа.

Что изменено (скрипт `tools/atlas_import.py`): переведены из координат RAS в оси проекта,
сглажены, подразделены и окрашены; из атласа взяты только щитовидная железа и перстневидный хрящ.
