// Required Notice: Copyright Matthew Armstrong (https://github.com/The-Dorkknight)
// Licensed under the PolyForm Noncommercial License 1.0.0. No warranty.

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

import UM 1.5 as UM
import Cura 1.1 as Cura

Item
{
    id: base
    width: column.width
    height: column.height

    readonly property int fieldWidth: Math.round(UM.Theme.getSize("setting_control").width * 0.45)
    readonly property int fieldHeight: UM.Theme.getSize("setting_control").height
    readonly property bool tethered: prop("HeadMode") === "tethers"

    function prop(name) { return UM.Controller.properties.getValue(name) }
    function setNum(name, text) { UM.Controller.setProperty(name, text.replace(",", ".")) }

    Column
    {
        id: column
        spacing: UM.Theme.getSize("default_margin").height

        GridLayout
        {
            id: grid
            columns: 4
            columnSpacing: UM.Theme.getSize("default_margin").width
            rowSpacing: UM.Theme.getSize("narrow_margin").height

            UM.Label { text: "Head" }
            Grid
            {
                Layout.columnSpan: 3
                columns: 3
                columnSpacing: UM.Theme.getSize("default_margin").width
                Cura.RadioButton
                {
                    text: "Cone"
                    checked: prop("HeadMode") === "cone"
                    onClicked: UM.Controller.setProperty("HeadMode", "cone")
                }
                Cura.RadioButton
                {
                    text: "Lobes"
                    checked: prop("HeadMode") === "lobes"
                    onClicked: UM.Controller.setProperty("HeadMode", "lobes")
                }
                Cura.RadioButton
                {
                    text: "Tethers"
                    checked: prop("HeadMode") === "tethers"
                    onClicked: UM.Controller.setProperty("HeadMode", "tethers")
                }
                Cura.RadioButton
                {
                    text: "Branch"
                    checked: prop("HeadMode") === "branch"
                    onClicked: UM.Controller.setProperty("HeadMode", "branch")
                }
                Cura.RadioButton
                {
                    text: "Solid"
                    checked: prop("HeadMode") === "trapezoid"
                    onClicked: UM.Controller.setProperty("HeadMode", "trapezoid")
                }
                Cura.RadioButton
                {
                    text: "Conform"
                    checked: prop("HeadMode") === "conform"
                    onClicked: UM.Controller.setProperty("HeadMode", "conform")
                }
            }

            UM.Label { text: "Inside the cone"; visible: prop("HeadMode") === "cone" }
            Row
            {
                Layout.columnSpan: 3
                visible: prop("HeadMode") === "cone"
                spacing: UM.Theme.getSize("default_margin").width
                Cura.RadioButton
                {
                    text: "Cross"
                    checked: prop("ConeFill") === "cross"
                    onClicked: UM.Controller.setProperty("ConeFill", "cross")
                }
                Cura.RadioButton
                {
                    text: "Rings"
                    checked: prop("ConeFill") === "rings"
                    onClicked: UM.Controller.setProperty("ConeFill", "rings")
                }
                Cura.RadioButton
                {
                    text: "None"
                    checked: prop("ConeFill") === "none"
                    onClicked: UM.Controller.setProperty("ConeFill", "none")
                }
            }

            UM.Label { text: "Tethers start"; visible: base.tethered }
            UM.TextFieldWithUnit
            {
                visible: base.tethered
                Layout.preferredWidth: base.fieldWidth; height: base.fieldHeight
                unit: "mm"
                text: prop("TetherHeight")
                onEditingFinished: setNum("TetherHeight", text)
            }
            UM.Label { text: "Coverage"; visible: base.tethered }
            UM.TextFieldWithUnit
            {
                visible: base.tethered
                Layout.preferredWidth: base.fieldWidth; height: base.fieldHeight
                unit: "%"
                text: prop("TetherCoverage")
                onEditingFinished: setNum("TetherCoverage", text)
            }
            UM.Label { text: "Bridge speed (0 = off)"; visible: base.tethered }
            UM.TextFieldWithUnit
            {
                visible: base.tethered
                Layout.preferredWidth: base.fieldWidth; height: base.fieldHeight
                unit: "mm/s"
                text: prop("BridgeSpeed")
                onEditingFinished: setNum("BridgeSpeed", text)
            }
            UM.CheckBox
            {
                visible: base.tethered
                Layout.columnSpan: 4
                text: "Cap stack: lattice, lattice, rings, diagonal"
                checked: prop("CapStack")
                onClicked: UM.Controller.setProperty("CapStack", checked)
            }
            UM.Label { text: "Cap flow (100 = off)"; visible: base.tethered }
            UM.TextFieldWithUnit
            {
                visible: base.tethered
                Layout.preferredWidth: base.fieldWidth; height: base.fieldHeight
                unit: "%"
                text: prop("CapFlow")
                onEditingFinished: setNum("CapFlow", text)
            }
            UM.Label
            {
                visible: base.tethered
                Layout.columnSpan: 4
                Layout.preferredWidth: grid.width
                wrapMode: Text.WordWrap
                text: "Experimental. Straight strips strung between two facing walls, starting that far below the overhang: the first and last at the two ends of the overhang (0.2 mm in), the rest evenly between covering about the Coverage share, every other layer shifted half a line so the strips snap off. The first layers are mid-air bridges, so on saving they are slowed to Bridge speed with the fan at 100%. The cap is a 4-layer stack written when you save: lattice across the tethers (at Cap flow, so it fuses with them instead of squashing them), lattice along them, a full layer of concentric rings at 50% fill, then a solid 100% top layer (not shown in Cura's preview). Changes Cura's Support X/Y Distance (0), Support Roof (on) and the support line direction or pattern; Remove puts them back."
                font: UM.Theme.getFont("small")
                color: UM.Theme.getColor("text_medium")
            }

            UM.Label { text: "Gussets (0 = off)" }
            UM.TextFieldWithUnit
            {
                Layout.preferredWidth: base.fieldWidth; height: base.fieldHeight
                unit: ""
                text: prop("GussetCount")
                onEditingFinished: setNum("GussetCount", text)
            }
            UM.Label { text: "Gusset height" }
            UM.TextFieldWithUnit
            {
                Layout.preferredWidth: base.fieldWidth; height: base.fieldHeight
                unit: "mm"
                enabled: prop("GussetCount") > 0
                text: prop("GussetHeight")
                onEditingFinished: setNum("GussetHeight", text)
            }

            UM.Label { text: "Gusset length" }
            UM.TextFieldWithUnit
            {
                Layout.preferredWidth: base.fieldWidth; height: base.fieldHeight
                unit: "mm"
                enabled: prop("GussetCount") > 0
                text: prop("GussetLength")
                onEditingFinished: setNum("GussetLength", text)
            }
            UM.Label { text: "Tube walls (lines)" }
            UM.TextFieldWithUnit
            {
                Layout.preferredWidth: base.fieldWidth; height: base.fieldHeight
                unit: ""
                text: prop("WallLines")
                onEditingFinished: setNum("WallLines", text)
            }

            UM.Label { text: prop("HeadMode") === "branch" ? "Gap between branches" : "Max bridge span" }
            UM.TextFieldWithUnit
            {
                Layout.preferredWidth: base.fieldWidth; height: base.fieldHeight
                unit: "mm"
                enabled: prop("HeadMode") === "cone" || prop("HeadMode") === "lobes" || base.tethered || prop("HeadMode") === "branch"
                text: prop("BridgeGap")
                onEditingFinished: setNum("BridgeGap", text)
            }
            UM.Label { text: "Contact Z gap" }
            UM.TextFieldWithUnit
            {
                Layout.preferredWidth: base.fieldWidth; height: base.fieldHeight
                unit: "mm"
                text: prop("ContactGap")
                onEditingFinished: setNum("ContactGap", text)
            }

            UM.Label { text: "Max tower radius" }
            UM.TextFieldWithUnit
            {
                Layout.preferredWidth: base.fieldWidth; height: base.fieldHeight
                unit: "mm"
                text: prop("MaxTowerRadius")
                onEditingFinished: setNum("MaxTowerRadius", text)
            }
            UM.Label { text: "Split spans over" }
            UM.TextFieldWithUnit
            {
                Layout.preferredWidth: base.fieldWidth; height: base.fieldHeight
                unit: "mm"
                text: prop("MaxSpan")
                onEditingFinished: setNum("MaxSpan", text)
            }

            UM.Label { text: "Overhang angle" }
            UM.TextFieldWithUnit
            {
                Layout.preferredWidth: base.fieldWidth; height: base.fieldHeight
                unit: "°"
                enabled: !prop("UseCuraAngle")
                text: prop("SupportAngle")
                onEditingFinished: setNum("SupportAngle", text)
            }
            UM.CheckBox
            {
                Layout.columnSpan: 2
                text: "Use Cura's angle"
                checked: prop("UseCuraAngle")
                onClicked: UM.Controller.setProperty("UseCuraAngle", checked)
            }

            UM.CheckBox
            {
                Layout.columnSpan: 4
                text: "Block Cura auto-support over towers"
                checked: prop("UseBlocker")
                onClicked: UM.Controller.setProperty("UseBlocker", checked)
            }
        }

        Row
        {
            spacing: UM.Theme.getSize("default_margin").width
            Cura.PrimaryButton
            {
                objectName: "hybridGenerate"
                text: "Generate"
                onClicked: UM.Controller.triggerAction("generateSupports")
            }
            Cura.SecondaryButton
            {
                objectName: "hybridRemove"
                text: "Remove"
                onClicked: UM.Controller.triggerAction("removeSupports")
            }
        }

        UM.Label
        {
            width: grid.width
            wrapMode: Text.WordWrap
            text: prop("Status")
        }

        UM.Label
        {
            width: grid.width
            wrapMode: Text.WordWrap
            text: prop("VersionText")
            font: UM.Theme.getFont("small")
            color: UM.Theme.getColor("text_medium")
        }
    }
}
