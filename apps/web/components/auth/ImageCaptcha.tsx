"use client";

import { useCallback, useEffect, useId, useState } from "react";
import { Loader2, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { authApi } from "@/lib/api";

type CaptchaResponse = {
  captcha_id: string;
  image: string;
};

export type ImageCaptchaValue = {
  captchaId: string;
  captchaAnswer: string;
};

type ImageCaptchaProps = {
  value: ImageCaptchaValue;
  onChange: (value: ImageCaptchaValue) => void;
  disabled?: boolean;
  reloadToken?: number;
  inputClassName?: string;
};

export function ImageCaptcha({ value, onChange, disabled, reloadToken = 0, inputClassName }: ImageCaptchaProps) {
  const inputId = useId();
  const [image, setImage] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const refreshCaptcha = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await authApi.get<CaptchaResponse>("/auth/captcha", {
        params: { t: Date.now() },
      });
      setImage(res.data.image);
      onChange({ captchaId: res.data.captcha_id, captchaAnswer: "" });
    } catch {
      setImage("");
      onChange({ captchaId: "", captchaAnswer: "" });
      setError("图形验证码加载失败");
    } finally {
      setLoading(false);
    }
  }, [onChange]);

  useEffect(() => {
    void refreshCaptcha();
  }, [refreshCaptcha, reloadToken]);

  return (
    <div className="space-y-2">
      <Label htmlFor={inputId} className="text-slate-700">
        Image code / 图形验证码
      </Label>
      <div className="grid grid-cols-[minmax(0,1fr)_44px] gap-2">
        <div className="flex h-[52px] min-h-[52px] items-center justify-center overflow-hidden rounded-md border border-slate-200 bg-white">
          {image ? (
            <img src={image} alt="图形验证码" className="h-[52px] w-full object-cover" draggable={false} />
          ) : (
            <span className="text-xs text-slate-500">{loading ? "加载中" : "验证码"}</span>
          )}
        </div>
        <Button
          type="button"
          variant="soft"
          size="icon"
          className="h-[52px] w-11"
          onClick={() => void refreshCaptcha()}
          disabled={disabled || loading}
          title="刷新图形验证码"
          aria-label="刷新图形验证码"
        >
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
        </Button>
      </div>
      <Input
        id={inputId}
        type="text"
        value={value.captchaAnswer}
        onChange={(event) => onChange({ ...value, captchaAnswer: event.target.value })}
        required
        autoComplete="off"
        inputMode="text"
        maxLength={8}
        placeholder="输入图形验证码"
        disabled={disabled || loading || !value.captchaId}
        className={inputClassName}
      />
      {error && <p className="text-xs text-red-600">{error}</p>}
    </div>
  );
}
