import { addSlideByNumber } from "./common.mjs";
export async function slide01(presentation, ctx) {
  return addSlideByNumber(1, presentation, ctx);
}
