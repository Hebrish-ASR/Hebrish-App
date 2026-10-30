package app.hebrish.dictation

import android.content.ActivityNotFoundException
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.widget.Toast

/**
 * Copy and Share for the screens that hold text (Try it, Transcription Mode, Install). One copy
 * of each, so an empty box says so instead of "Copied" with nothing on the clipboard (Copy) or
 * doing nothing at all (Share), as both screens did up to 1.008.
 */
object TextOut {
    fun copy(ctx: Context, text: CharSequence) {
        if (text.isBlank()) return toast(ctx, R.string.try_nothing_to_copy)
        ctx.getSystemService(ClipboardManager::class.java)
            .setPrimaryClip(ClipData.newPlainText(ctx.getString(R.string.app_name), text))
        toast(ctx, R.string.try_copied)
    }

    fun share(ctx: Context, text: CharSequence) {
        if (text.isBlank()) return toast(ctx, R.string.try_nothing_to_share)
        val send = Intent(Intent.ACTION_SEND).setType("text/plain").putExtra(Intent.EXTRA_TEXT, text.toString())
        try {
            ctx.startActivity(Intent.createChooser(send, ctx.getString(R.string.try_share)))
        } catch (_: ActivityNotFoundException) {
            toast(ctx, R.string.try_nothing_to_share)
        }
    }

    private fun toast(ctx: Context, res: Int) = Toast.makeText(ctx, res, Toast.LENGTH_SHORT).show()
}
