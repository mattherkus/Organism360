# Анатомические 3D-модели

Модели органов в этой папке (`*.npz` — геометрия, `*.json` — группы, цвета и источник в поле
`attribution`) получены из четырёх открытых источников. В окне 3D-просмотра под каждой моделью
выводится подпись её источника.

| Источник | Органы | Лицензия |
|---|---|---|
| BodyParts3D | сердце, мозг, желудок, кишечник, почки, поджелудочная железа, надпочечники, пищевод, прямая кишка, аппендикс, трахея, аорта, полые вены, диафрагма, гипофиз, тимус | CC BY 4.0 |
| Human Reference Atlas (HuBMAP) | матка, яичники, мочевой пузырь, лимфатический узел | CC BY 4.0 |
| Атлас головы и шеи SPL / Open Anatomy | щитовидная железа | 3D Slicer License, часть B |
| Z-Anatomy | спинной мозг, печень, жёлчный пузырь, лёгкие, предстательная железа, селезёнка | CC BY-SA 4.0 |

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
- коронарные сосуды сердца выдвинуты на 1 мм наружу;
- части окрашены по названиям и объединены в группы материалов;
- для ориентира к некоторым органам добавлены соседние: к надпочечникам — почки,
  к пищеводу — желудок, к аппендиксу — слепая кишка, к трахее — главные бронхи;
- у аорты оставлены только начала ветвей (плечеголовной ствол, левые общая сонная и подключичная артерии,
  чревный ствол, верхняя брыжеечная, почечные и общие подвздошные артерии), у полых вен — впадающие в них
  плечеголовные, общие подвздошные, печёночные и непарная вены: в понятия базы входит всё дерево сосудов.

Щитовидной железы, селезёнки, матки, яичников и лимфатических узлов в BodyParts3D 4.0 нет, у спинного мозга
там только центральный канал, а у лёгких нет поверхности (только бронхиальное дерево и сосуды).
Печень, жёлчный пузырь, мочевой пузырь и лёгкие из BodyParts3D заменены моделями других источников;
их правила остались в скрипте и собираются, если назвать орган явно.

## Human Reference Atlas (HuBMAP)

**3D Reference Organs of the Human Reference Atlas, Human BioMolecular Atlas Program (HuBMAP);
organs based on the Visible Human Project of the U.S. National Library of Medicine, lymph node model
by Li Yao and Kristen Browne (NIH); licensed under CC Attribution 4.0 International**

- библиотека: https://humanatlas.io/3d-reference-library
- лицензия: https://creativecommons.org/licenses/by/4.0/
- исходные файлы (`https://cdn.humanatlas.io/digital-objects/ref-organ/<орган>/<версия>/assets/<файл>`):
  `uterus-female/v1.2/3d-vh-f-uterus.glb`, `ovary-female-left/v1.3/3d-vh-f-ovary-l.glb`,
  `ovary-female-right/v1.3/3d-vh-f-ovary-r.glb`, `fallopian-tube-female-left/v1.2/3d-vh-f-fallopian-tube-l.glb`,
  `fallopian-tube-female-right/v1.2/3d-vh-f-fallopian-tube-r.glb`,
  `urinary-bladder-male/v1.2/3d-vh-m-urinary-bladder.glb`, `lymph-node-male/v1.4/3d-nih-m-lymph-node.glb`

Что изменено (скрипт `tools/atlas_import.py`):

- переведены из метров и осей glTF в миллиметры и оси проекта, затем — в единицы сцены;
- лоскуты одной поверхности (части матки и маточных труб, дно и основание мочевого пузыря) сварены
  по общим вершинам в одну сетку;
- упрощены, сглажены и очищены от невидимых снаружи частей так же, как модели BodyParts3D;
- матка и яичники собраны в одну сцену с маточными трубами (у модели яичников матка и трубы приглушены);
- у мочевого пузыря убраны устья мочеточников (они внутри);
- у лимфатического узла убрана капсула, чтобы было видно его строение: фолликулы, паракортекс,
  мозговое вещество, кровеносные и лимфатические сосуды;
- части окрашены и объединены в группы материалов.

Лёгкие, селезёнка и предстательная железа раньше тоже были из Human Reference Atlas
(`lung-male/v1.4`, `spleen-male/v1.3`, `prostate-male/v1.2`); их правила остались в скрипте под именами
`lungs_hra`, `spleen_hra`, `prostate_hra`.

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

## Z-Anatomy

**Z-Anatomy — The libre 3D atlas of anatomy, licensed under CC Attribution-ShareAlike 4.0 International;
based on BodyParts3D, © The Database Center for Life Science**

- проект: https://github.com/Z-Anatomy/Models-of-human-anatomy (условия: `License.txt` там же)
- лицензия: https://creativecommons.org/licenses/by-sa/4.0/
- исходные файлы (`https://raw.githubusercontent.com/LluisV/Z-Anatomy/PC-Version/Resources/Models/FBX/<файл>`):
  `NervousSystem100.fbx` (спинной мозг), `VisceralSystem100.fbx` (печень, жёлчный пузырь, лёгкие,
  предстательная железа), `LymphoidOrgans100.fbx` (селезёнка)

Что изменено (скрипт `tools/atlas_import.py`):

- переведены из сантиметров и осей FBX в миллиметры и оси проекта, затем — в единицы сцены;
- упрощены, сглажены и очищены от невидимых снаружи частей так же, как модели BodyParts3D
  (у лёгких — бронхи внутри долей, у предстательной железы — семявыбрасывающие протоки);
- у спинного мозга взяты наружная поверхность белого вещества, передние и задние корешки,
  спинномозговые узлы и конский хвост;
- к жёлчному пузырю добавлен жёлчный проток, к лёгким — трахея и главные бронхи,
  к предстательной железе — семенные пузырьки и семявыносящие протоки;
- части окрашены и объединены в группы материалов.

Условие ShareAlike: модели `spinal_cord`, `liver`, `gallbladder`, `lungs`, `prostate`, `spleen`
(`*.npz` и `*.json`) — производные от Z-Anatomy и распространяются под той же лицензией
CC BY-SA 4.0 с этой атрибуцией. На остальные файлы и код программы это условие не распространяется.
