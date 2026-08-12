import { useState } from "react";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Collapse from "@mui/material/Collapse";
import IconButton from "@mui/material/IconButton";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemText from "@mui/material/ListItemText";
import Typography from "@mui/material/Typography";
import ExpandLessIcon from "@mui/icons-material/ExpandLess";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";

import { DishRecipeEditor } from "../../components/menu/DishRecipeEditor";
import { RowsSkeleton } from "../../components/shell/RowsSkeleton";
import { ApiError } from "../../services/httpClient";
import { useCategories, useDishes } from "../../services/menuService";

/**
 * The Menu Management surface (Story 2.3).
 *
 * Lists every Dish; each row expands into its own recipe editor
 * (DishRecipeEditor), where an Admin adds/edits/removes Recipe Ingredient
 * lines and toggles availability. Category/Dish creation forms are
 * deliberately out of scope, no acceptance criterion in this story tests
 * them, per key-menu-management.html this screen's remaining CRUD ships in
 * a later story.
 *
 * @returns The Menu Management page.
 */
export function MenuManagementPage() {
  const [expandedDishId, setExpandedDishId] = useState<number | null>(null);
  const { data: dishes, isLoading, isError, error, refetch } = useDishes();
  const { data: categories } = useCategories();

  const categoryName = (categoryId: number) =>
    categories?.find((category) => category.id === categoryId)?.name ?? `#${categoryId}`;

  return (
    <>
      <Typography variant="h5" component="h1" gutterBottom>
        Menu Management
      </Typography>

      {isLoading && <RowsSkeleton count={5} />}

      {isError && (
        <Alert
          severity="error"
          action={
            <Button color="inherit" size="small" onClick={() => refetch()}>
              Retry
            </Button>
          }
        >
          {`Could not load the menu. ${error instanceof ApiError ? error.message : "Try again."}`}
        </Alert>
      )}

      {!isLoading && !isError && dishes?.length === 0 && (
        <Typography color="text.secondary">No dishes yet.</Typography>
      )}

      {!isLoading && !isError && dishes && dishes.length > 0 && (
        <List>
          {dishes.map((dish) => {
            const isExpanded = expandedDishId === dish.id;
            return (
              // component="div" because MUI's ListItem renders an <li> by
              // default; nesting that inside our own <li> would make the
              // parser auto-close the outer one and move the Collapse panel
              // out of the list item it belongs to.
              <ListItem key={dish.id} component="div" sx={{ display: "block" }} disableGutters>
                <ListItem
                  component="div"
                  secondaryAction={
                    <IconButton
                      aria-label={isExpanded ? `Collapse ${dish.name}` : `Expand ${dish.name}`}
                      onClick={() => setExpandedDishId(isExpanded ? null : dish.id)}
                    >
                      {isExpanded ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                    </IconButton>
                  }
                >
                  <ListItemText primary={dish.name} secondary={categoryName(dish.category_id)} />
                  <Chip
                    size="small"
                    label={dish.is_available ? "Available" : "Unavailable"}
                    color={dish.is_available ? "success" : "default"}
                    sx={{ marginRight: 2 }}
                  />
                </ListItem>
                <Collapse in={isExpanded} unmountOnExit>
                  <DishRecipeEditor dish={dish} />
                </Collapse>
              </ListItem>
            );
          })}
        </List>
      )}
    </>
  );
}
