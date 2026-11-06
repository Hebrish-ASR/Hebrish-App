package app.hebrish.dictation

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class MicOrderTest {
    @Test fun nothingSavedIsTheDefault() = assertEquals(MicOrder.DEFAULT, MicOrder.parse(null))

    @Test fun roundTrips() {
        val order = listOf(MicKind.PHONE, MicKind.WIRED, MicKind.USB, MicKind.BLUETOOTH)
        assertEquals(order, MicOrder.parse(MicOrder.encode(order)))
    }

    @Test fun unknownAndRepeatedNamesAreDroppedAndMissingKindsAdded() = assertEquals(
        listOf(MicKind.PHONE, MicKind.USB, MicKind.BLUETOOTH, MicKind.WIRED),
        MicOrder.parse("PHONE,LASER,PHONE"),
    )

    @Test fun promoteMovesAKindToTheFront() = assertEquals(
        listOf(MicKind.PHONE, MicKind.USB, MicKind.BLUETOOTH, MicKind.WIRED),
        MicOrder.promote(MicOrder.DEFAULT, MicKind.PHONE),
    )

    @Test fun rankPutsUsbAheadOfBluetoothByDefault() {
        val kinds = mapOf("buds" to MicKind.BLUETOOTH, "phone" to MicKind.PHONE, "usb" to MicKind.USB)
        assertEquals(listOf("usb", "buds", "phone"), MicOrder.rank(listOf("phone", "buds", "usb"), MicOrder.DEFAULT) { kinds[it] })
    }

    @Test fun rankFollowsTheUsersOrderAndKeepsUnknownsLast() {
        val kinds = mapOf("buds" to MicKind.BLUETOOTH, "usb" to MicKind.USB)
        val order = MicOrder.promote(MicOrder.DEFAULT, MicKind.BLUETOOTH)
        assertEquals(listOf("buds", "usb", "other"), MicOrder.rank(listOf("other", "usb", "buds"), order) { kinds[it] })
    }

    @Test fun sessionLapsesAfterItsWindow() {
        assertTrue(MicOrder.sessionLive(1_000, 1_000 + MicOrder.SESSION_MS - 1))
        assertFalse(MicOrder.sessionLive(1_000, 1_000 + MicOrder.SESSION_MS))
        assertFalse("a clock set back ends it", MicOrder.sessionLive(1_000, 999))
    }
}
