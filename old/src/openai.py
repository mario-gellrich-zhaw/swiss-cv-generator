# Local shim so legacy import openai still works and maps ChatCompletion to the new shim.
# This resolves import openai; openai.ChatCompletion.create(...) calls to the local compat layer.
try:
    from swiss_cv.openai_compat import ChatCompletion as ChatCompletionCompat
except Exception:
    ChatCompletionCompat = None

ChatCompletion = ChatCompletionCompat


