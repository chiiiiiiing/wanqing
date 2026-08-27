export async function hello({ name }) {
  return { success: true, message: `Hello, ${name || "world"}!` };
}
